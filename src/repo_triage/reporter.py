"""Build a deterministic briefing shared by terminal and Markdown output."""

from collections import Counter
from datetime import datetime, timezone
import html
import re

from rich.console import Console
from rich.markdown import Markdown

from repo_triage.llm_client import rank_triage
from repo_triage.models import Issue, IssueTriage

_NOTICE = (
    "AI-assisted suggestions, not authoritative severity determinations. "
    "Maintainers should verify evidence and impact."
)


def _escape(text: str) -> str:
    """Keep untrusted text on one line and escape Markdown and HTML markup."""
    text = html.escape(" ".join(text.split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", text)


def build_digest(
    repository: str,
    issues: list[Issue],
    results: list[IssueTriage],
    requested_limit: int = 15,
    generated_at: datetime | None = None,
) -> str:
    """Build a Markdown briefing from validated triage without an LLM call.

    Args:
        repository: Validated owner/repo identifier.
        issues: Sampled source issues with original titles and URLs.
        results: Validated triage results matching the source issues exactly.
        requested_limit: Maximum issue count requested by the user.
        generated_at: Optional timezone-aware timestamp for reproducible output.

    Returns:
        A Markdown report with deterministic summary, priorities, and counts.

    Raises:
        ValueError: If source and result issue numbers do not match exactly.
    """
    sources = {issue.number: issue for issue in issues}
    numbers = [result.issue_number for result in results]
    if (
        len(sources) != len(issues)
        or len(numbers) != len(sources)
        or set(numbers) != set(sources)
    ):
        raise ValueError("Report requires one triage result per source issue.")
    ranked = rank_triage(results, issues)
    categories = Counter(result.category for result in ranked)
    urgencies = Counter(result.urgency for result in ranked)
    timestamp = generated_at or datetime.now(timezone.utc)
    lines = [
        f"# Monday briefing: {_escape(repository)}",
        "", "## Repository and analysis scope", "",
        f"- Repository: https://github.com/{repository}",
        f"- Analyzed: {len(ranked)} open issues (requested up to "
        f"{requested_limit}); pull requests excluded.",
        "- Sorting: sampled by most recently updated first; priorities ranked "
        "by urgency, priority labels, comment count, then issue number.",
        "- Sampling limitation: at most two GitHub pages of 100 entries, "
        "with at most 15 actual issues analyzed. This is a recent-activity "
        "sample, not a full backlog audit; older urgent issues may be missed. "
        "Issue bodies are truncated to 800 characters.",
        "- Generated at: "
        f"{timestamp.astimezone(timezone.utc).isoformat()} (UTC).",
        "", "## Executive summary", "",
    ]
    if ranked:
        counts = ", ".join(
            f"{urgencies[level]} {level}"
            for level in ("critical", "high", "medium", "low")
        )
        lines.append(
            f"The {len(ranked)} sampled issues include "
            f"{categories['bug']} bug reports. Suggested urgency: {counts}. "
            f"Start by reviewing #{ranked[0].issue_number}."
        )
    else:
        lines.append(
            "No issues were returned within the sampled pages. "
            "No LLM analysis was needed; this does not establish that the "
            "repository has no open issues."
        )
    lines.extend(["", "## Top 5 priorities", ""])
    if not ranked:
        lines.append("No sampled issues to prioritize.")
    for index, result in enumerate(ranked[:5], start=1):
        source = sources[result.issue_number]
        # URLs come from the source, never from the LLM. Encode delimiters.
        url = str(source.html_url).replace("(", "%28").replace(")", "%29")
        lines.extend([
            f"### {index}. #{source.number}: {_escape(source.title)}",
            "",
            f"- URL: {url}",
            f"- Urgency: {result.urgency}",
            f"- Rationale: {_escape(result.rationale)}",
            f"- Next action: {_escape(result.next_action)}",
            "",
        ])
    lines.extend(["", "## Category counts", ""])
    lines.extend(
        f"- {category}: {categories[category]}"
        for category in ("bug", "feature", "docs", "question", "other")
    )
    lines.extend(["", f"**{_NOTICE}**", ""])
    return "\n".join(lines)


def print_digest(digest: str, console: Console) -> None:
    """Render the shared Markdown briefing as concise Rich terminal output."""
    console.print(Markdown(digest))
