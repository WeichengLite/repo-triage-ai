"""Unit tests for bounded, credential-safe GitHub fetching."""

from unittest.mock import Mock, patch

import pytest
import requests

from repo_triage.github_client import GitHubClient, GitHubError, validate_repository


def make_issue(number: int = 1) -> dict:
    """Build an API issue fixture."""
    return {
        "number": number, "title": "An issue", "body": "x" * 900,
        "labels": [{"name": "bug"}], "comments": 3,
        "updated_at": "2026-10-28T10:00:00Z",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
    }


def response(rows: object, status: int = 200) -> Mock:
    """Build a mock HTTP response."""
    return Mock(status_code=status, json=Mock(return_value=rows))


@pytest.mark.parametrize("repository", ["", "owner", "a/b/c", "https://github.com/a/b", "a/..", "-a/b", "a/b?x", "a--b/c"])
def test_invalid_repository(repository: str) -> None:
    with pytest.raises(ValueError):
        validate_repository(repository)


@pytest.mark.parametrize("repository", [
    "pallets/flask", "python/cpython", "owner-name/repo_name.v2",
])
def test_valid_repository(repository: str) -> None:
    """Accept valid identifiers without changing their case or spelling."""
    assert validate_repository(repository) == repository


@pytest.mark.parametrize("limit", [0, 31, -1, True, 1.5, "15"])
def test_invalid_limit(limit: object) -> None:
    with patch("repo_triage.github_client.requests.get") as get:
        with pytest.raises(ValueError):
            GitHubClient().fetch_open_issues("owner/repo", limit=limit)
        get.assert_not_called()


def test_default_limit_excludes_pull_requests_and_extracts_fields() -> None:
    rows = [{"pull_request": {}}] + [make_issue(i) for i in range(1, 21)]
    with patch("repo_triage.github_client.requests.get", return_value=response(rows)) as get:
        issues = GitHubClient().fetch_open_issues("owner/repo")
    assert len(issues) == 15
    assert issues[0].number == 1
    assert issues[0].title == "An issue"
    assert issues[0].body == "x" * 800
    assert issues[0].labels == ["bug"]
    assert issues[0].comment_count == 3
    assert issues[0].updated_at.year == 2026
    assert str(issues[0].html_url).endswith("/issues/1")
    assert get.call_args.kwargs["timeout"] == 10
    assert get.call_args.kwargs["params"] == {
        "state": "open", "sort": "updated", "direction": "desc",
        "per_page": 100, "page": 1,
    }
    assert "Authorization" not in get.call_args.kwargs["headers"]


def test_second_page_counts_actual_issues_and_deduplicates() -> None:
    first = [{"pull_request": {}} for _ in range(99)] + [make_issue(1)]
    second = [make_issue(i) for i in range(1, 40)]
    with patch("repo_triage.github_client.requests.get", side_effect=[response(first), response(second)]) as get:
        issues = GitHubClient(token="secret").fetch_open_issues("owner/repo", 30)
    assert [issue.number for issue in issues] == list(range(1, 31))
    assert get.call_count == 2
    assert get.call_args.kwargs["params"]["page"] == 2
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"


def test_two_page_budget() -> None:
    with patch("repo_triage.github_client.requests.get", return_value=response([{"pull_request": {}}] * 100)) as get:
        assert GitHubClient().fetch_open_issues("owner/repo") == []
    assert get.call_count == 2


def test_null_body_and_empty_repository() -> None:
    row = make_issue()
    row["body"] = None
    with patch("repo_triage.github_client.requests.get", return_value=response([row])):
        assert GitHubClient().fetch_open_issues("owner/repo")[0].body == ""
    with patch("repo_triage.github_client.requests.get", return_value=response([])) as get:
        assert GitHubClient().fetch_open_issues("owner/repo") == []
    get.assert_called_once()


@pytest.mark.parametrize("status", [403, 404, 429, 500, 401, 301])
def test_http_errors_do_not_expose_response(status: int) -> None:
    with patch("repo_triage.github_client.requests.get", return_value=response("secret", status)):
        with pytest.raises(GitHubError) as caught:
            GitHubClient(token="secret").fetch_open_issues("owner/repo")
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("error", [requests.Timeout("secret"), requests.ConnectionError("secret")])
def test_network_errors_are_safe(error: requests.RequestException) -> None:
    with patch("repo_triage.github_client.requests.get", side_effect=error):
        with pytest.raises(GitHubError) as caught:
            GitHubClient().fetch_open_issues("owner/repo")
    assert "secret" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("data", [{}, [None], [{}], [{**make_issue(), "labels": None}]])
def test_malformed_data(data: object) -> None:
    with patch("repo_triage.github_client.requests.get", return_value=response(data)):
        with pytest.raises(GitHubError):
            GitHubClient().fetch_open_issues("owner/repo")


def test_invalid_json() -> None:
    result = response(None)
    result.json.side_effect = ValueError("secret")
    with patch("repo_triage.github_client.requests.get", return_value=result):
        with pytest.raises(GitHubError, match="invalid JSON"):
            GitHubClient().fetch_open_issues("owner/repo")
