"""Fetch, triage, and report a bounded sample of public GitHub issues."""

import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import litellm
from dotenv import load_dotenv
from rich.console import Console

from repo_triage.github_client import (
    GitHubClient,
    GitHubError,
    validate_repository,
)
from repo_triage.llm_client import LiteLLMProvider, TriageClient, TriageError
from repo_triage.reporter import (
    ExportError,
    build_digest,
    check_export_support,
    export_digest,
    print_digest,
)


def _parse_since(value: str) -> timedelta:
    """Parse a positive day duration such as 7d for argparse."""
    if not re.fullmatch(r"[1-9][0-9]*d", value):
        raise argparse.ArgumentTypeError(
            "--since must be positive days, e.g. 7d"
        )
    try:
        return timedelta(days=int(value[:-1]))
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError(
            "--since is outside the supported range"
        ) from None


def main() -> int:
    """Print a briefing, optionally export Markdown, and return a status."""
    parser = argparse.ArgumentParser(
        description="Generate an AI-assisted briefing of recent GitHub issues."
    )
    parser.add_argument(
        "repository", help="Public GitHub repository: owner/repo"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Issue count (1–15; default: 15)",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Save dated report files in reports/",
    )
    parser.add_argument(
        "--format",
        choices=("md", "docx", "both"),
        default="md",
        help="Export format (requires --export; default: md)",
    )
    parser.add_argument(
        "--model", help="LiteLLM model (overrides LLM_MODEL and the default)"
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        metavar="Nd",
        help="Only issues updated after N days ago, e.g. 7d (UTC)",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 15:
        parser.error("--limit must be between 1 and 15")
    if args.model is not None and not args.model.strip():
        parser.error("--model must not be empty")
    try:
        since = (
            datetime.now(timezone.utc).replace(microsecond=0) - args.since
            if args.since is not None
            else None
        )
    except OverflowError:
        parser.error("--since is outside the supported date range")
    exported: list[Path] = []
    try:
        repository = validate_repository(args.repository)
        if args.export:
            check_export_support(args.format)
        # Explicit shell variables take precedence over the local .env file.
        load_dotenv(dotenv_path=Path(".env"), override=False)
        client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        issues = client.fetch_open_issues(
            repository, limit=args.limit, since=since
        )
        # Keep expected provider failures to the safe application error below.
        litellm.suppress_debug_info = True
        provider = LiteLLMProvider(model=args.model)
        if issues:
            try:
                _, provider_name, _, _ = litellm.get_llm_provider(
                    model=provider.model
                )
            except Exception:
                raise TriageError(
                    "Could not resolve the model provider; check --model "
                    "or LLM_MODEL."
                ) from None
            if (
                provider_name == "openai"
                and not os.getenv("OPENAI_API_KEY", "").strip()
            ):
                raise TriageError(
                    "OPENAI_API_KEY is missing. Add it to the local .env "
                    "file or export it in your shell.",
                    category="authentication",
                )
        results = TriageClient(provider).triage(issues)
        generated_at = datetime.now(timezone.utc)
        digest = build_digest(
            repository,
            issues,
            results,
            args.limit,
            generated_at=generated_at,
            since=since,
            limit_reason=client.limit_reason,
        )
        if args.export:
            exported = export_digest(
                digest, repository, generated_at, args.format
            )
    except ExportError as error:
        Console(stderr=True).print(
            f"Export failed: {error}", markup=False, highlight=False
        )
        return 1
    except TriageError as error:
        Console(stderr=True).print(
            f"Triage failed ({error.category}): {error}",
            markup=False,
            highlight=False,
        )
        return 1
    except (ValueError, GitHubError) as error:
        Console(stderr=True).print(str(error), markup=False, highlight=False)
        return 1
    except OSError:
        Console(stderr=True).print(
            "Could not export report; check directory permissions.",
            markup=False,
        )
        return 1
    print_digest(digest, Console())
    for path in exported:
        Console().print(f"Exported {path}", markup=False)
    return 0
