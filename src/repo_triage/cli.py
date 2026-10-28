"""Command-line entry point for fetching and optionally triaging issues."""

import argparse
import os

from rich.console import Console

from repo_triage.github_client import GitHubClient, GitHubError
from repo_triage.llm_client import TriageClient, TriageError


def main() -> int:
    """Fetch issues as JSON and return a shell exit status."""
    parser = argparse.ArgumentParser(
        description="Fetch recent open GitHub issues."
    )
    parser.add_argument(
        "repository", help="Public GitHub repository: owner/repo"
    )
    parser.add_argument(
        "--limit", type=int, default=15,
        help="Issue count (1–30; default: 15)",
    )
    parser.add_argument(
        "--triage", action="store_true",
        help="Analyze and rank up to 15 issues using LLM_MODEL",
    )
    args = parser.parse_args()
    if args.triage and not 1 <= args.limit <= 15:
        parser.error("--triage requires --limit between 1 and 15")
    try:
        client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        issues = client.fetch_open_issues(args.repository, limit=args.limit)
    except (ValueError, GitHubError) as error:
        Console(stderr=True).print(str(error), markup=False, highlight=False)
        return 1
    if args.triage:
        try:
            results = TriageClient().triage(issues)
        except TriageError as error:
            Console(stderr=True).print(
                str(error), markup=False, highlight=False
            )
            return 1
        Console().print_json(
            data=[result.model_dump() for result in results]
        )
        return 0
    Console().print_json(
        data=[issue.model_dump(mode="json") for issue in issues]
    )
    return 0
