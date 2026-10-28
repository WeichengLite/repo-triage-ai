"""Fetch a bounded set of open issues from the public GitHub API."""

import re
from datetime import datetime, timezone
from typing import Any, Literal

import requests
from pydantic import ValidationError

from repo_triage.models import Issue


class GitHubError(Exception):
    """A safe, user-facing error while communicating with GitHub."""


def validate_repository(repository: str) -> str:
    """Validate an owner/repo identifier.

    Args:
        repository: A GitHub owner/repo identifier, without a URL prefix.

    Returns:
        The validated identifier.

    Raises:
        ValueError: If the identifier is malformed.
    """
    parts = repository.split("/")
    if len(parts) != 2:
        raise ValueError("Repository must use owner/repo format.")
    owner, name = parts
    if (
        not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner
        )
        or "--" in owner
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)
        or name in {".", ".."}
    ):
        raise ValueError("Repository must contain a valid owner and name.")
    return repository


class GitHubClient:
    """Read public repository issues using optional token authentication."""

    def __init__(self, token: str | None = None) -> None:
        """Initialize the client with an optional GitHub token."""
        self.limit_reason: Literal["issue_limit", "page_limit"] | None = None
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def fetch_open_issues(
        self, repository: str, limit: int = 15, since: datetime | None = None
    ) -> list[Issue]:
        """Fetch recent issues, excluding pull requests, from at most two pages.

        Args:
            repository: A public GitHub owner/repo identifier.
            limit: Maximum actual issues to return, between 1 and 30.
            since: Optional timezone-aware exclusive update cutoff.

        Returns:
            Issues in descending update order. May contain fewer than limit
            when the repository or two-page budget is exhausted.

        Raises:
            ValueError: If the repository, limit, or cutoff is invalid.
            GitHubError: If GitHub is unavailable or returns invalid data.
        """
        repository = validate_repository(repository)
        self.limit_reason = None
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 30
        ):
            raise ValueError("Issue limit must be an integer between 1 and 30.")
        if since is not None:
            if since.utcoffset() is None:
                raise ValueError("The update cutoff must include a timezone.")
            since = since.astimezone(timezone.utc)
        issues: list[Issue] = []
        seen: set[int] = set()
        for page in range(1, 3):
            rows = self._fetch_page(repository, page, since)
            try:
                for row in rows:
                    if "pull_request" in row:
                        continue
                    issue = Issue(
                        number=row["number"],
                        title=row["title"],
                        body=(row.get("body") or "")[:800],
                        labels=[label["name"] for label in row["labels"]],
                        comment_count=row["comments"],
                        updated_at=row["updated_at"],
                        html_url=row["html_url"],
                    )
                    if issue.updated_at.utcoffset() is None:
                        raise GitHubError(
                            "GitHub returned a timestamp without a timezone."
                        )
                    issue.updated_at = issue.updated_at.astimezone(timezone.utc)
                    if since is not None and issue.updated_at <= since:
                        continue
                    if issue.number not in seen:
                        issues.append(issue)
                        seen.add(issue.number)
                    if len(issues) == limit:
                        self.limit_reason = "issue_limit"
                        return issues
            except (KeyError, TypeError, ValidationError):
                raise GitHubError(
                    "GitHub returned invalid issue data."
                ) from None
            if len(rows) < 100:
                break
            if page == 2:
                self.limit_reason = "page_limit"
        return issues

    def _fetch_page(
        self, repository: str, page: int, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Fetch one fixed-size page and translate failures to safe errors."""
        params: dict[str, str | int] = {
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
            "page": page,
        }
        if since is not None:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            response = requests.get(
                f"https://api.github.com/repos/{repository}/issues",
                headers=self._headers,
                params=params,
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise GitHubError(
                "Unable to reach GitHub; check your connection and retry."
            ) from None
        if response.status_code == 403:
            raise GitHubError(
                "GitHub denied access or its API rate limit was reached."
            )
        if response.status_code == 404:
            raise GitHubError(
                "Repository not found or not publicly accessible."
            )
        if response.status_code == 429:
            raise GitHubError("GitHub rate limit reached; retry later.")
        if response.status_code != 200:
            raise GitHubError(
                f"GitHub request failed (HTTP {response.status_code})."
            )
        try:
            data = response.json()
        except ValueError:
            raise GitHubError("GitHub returned invalid JSON.") from None
        if not isinstance(data, list) or any(
            not isinstance(row, dict) for row in data
        ):
            raise GitHubError("GitHub returned invalid issue data.")
        return data
