"""Fetch, triage, and report a bounded sample of public GitHub issues."""

import argparse
import os
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
from repo_triage.reporter import build_digest, print_digest


def main() -> int:
    """Print a briefing, optionally export Markdown, and return a status."""
    parser = argparse.ArgumentParser(
        description="Generate an AI-assisted briefing of recent GitHub issues."
    )
    parser.add_argument(
        "repository", help="Public GitHub repository: owner/repo"
    )
    parser.add_argument(
        "--limit", type=int, default=15,
        help="Issue count (1–15; default: 15)",
    )
    parser.add_argument(
        "--export", action="store_true",
        help="Write MONDAY_DIGEST.md in the current directory",
    )
    parser.add_argument(
        "--model", help="LiteLLM model (overrides LLM_MODEL and the default)"
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 15:
        parser.error("--limit must be between 1 and 15")
    if args.model is not None and not args.model.strip():
        parser.error("--model must not be empty")
    try:
        repository = validate_repository(args.repository)
        # Explicit shell variables take precedence over the local .env file.
        load_dotenv(dotenv_path=Path(".env"), override=False)
        client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        issues = client.fetch_open_issues(repository, limit=args.limit)
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
            if provider_name == "openai" and not os.getenv(
                "OPENAI_API_KEY", ""
            ).strip():
                raise TriageError(
                    "OPENAI_API_KEY is missing. Add it to the local .env "
                    "file or export it in your shell.",
                    category="authentication",
                )
        results = TriageClient(provider).triage(issues)
        digest = build_digest(repository, issues, results, args.limit)
        if args.export:
            Path("MONDAY_DIGEST.md").write_text(digest, encoding="utf-8")
    except TriageError as error:
        Console(stderr=True).print(
            f"Triage failed ({error.category}): {error}",
            markup=False, highlight=False,
        )
        return 1
    except (ValueError, GitHubError) as error:
        Console(stderr=True).print(str(error), markup=False, highlight=False)
        return 1
    except OSError:
        Console(stderr=True).print(
            "Could not write MONDAY_DIGEST.md; check directory permissions.",
            markup=False,
        )
        return 1
    print_digest(digest, Console())
    if args.export:
        Console().print("Exported MONDAY_DIGEST.md", markup=False)
    return 0
