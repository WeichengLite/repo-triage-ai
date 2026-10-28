# repo-triage-ai

Turn recent GitHub issues into a short briefing with up to five suggested priorities, source links, and concrete next actions.

## Why this tool?

Recently updated does not always mean important. Maintainers need to spot reported bugs and regressions without reading another wall of AI text. This tool suggests what to review next; you decide what matters.

## What matters most

These are design goals, not guarantees of accuracy or security.

| Perspective | Wants | Wants to avoid |
|---|---|---|
| Customer: maintainer | A short, actionable priority list | Invented urgency, false critical alerts, verbose summaries |
| Builder: platform team | Bounded cost and execution, simple code, swappable providers | Agent loops, repeated calls, provider lock-in |
| Security: governance | Read-only access, local secrets, traceable suggestions | Leaked keys, destructive actions, autonomous GitHub posts |

## Quick Start

You need **Python 3.10+**, internet access, and a large language model (LLM) API key. From a fresh checkout:

```sh
cd repo-triage-ai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Edit `.env` with your key:

```dotenv
LLM_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your_actual_key_here
```

`.env` is ignored by Git. Keep keys local. The CLI reads it from the current directory; exported variables take precedence. `GITHUB_TOKEN` is optional.

Generate a briefing from issues updated after seven days ago:

```sh
repo-triage python/cpython --limit 5 --since 7d --export
```

Omit `--since` for no date filter. It accepts positive whole days and uses an exclusive UTC cutoff. `--limit` accepts 1–15; the default is 15. Without `--export`, output stays in the terminal.

Exports go into `reports/` as `{repo}_triage_YYYY-MM-DD.md`, using the UTC generation date. Existing names get an `_HHMMSS` suffix, then a number for repeated collisions.

For Word output, install the optional extra and choose `md`, `docx`, or `both`:

```sh
python -m pip install -e '.[word]'
repo-triage python/cpython --limit 5 --since 7d --export --format both
```

Both formats reuse one report without extra LLM calls; Markdown is the default.

`--model` overrides `LLM_MODEL`. For Anthropic, use `anthropic/<your-enabled-model-id>` and `ANTHROPIC_API_KEY`. Replace the placeholder with a model your account supports. Only OpenAI has been verified live.

Test with `pytest -q`; Word tests need the extra. Live-model tests require opt-in. [Verification notes](examples/audit_notes.md).

## What You Get

Briefings show scope, UTC generation and issue-update times, a summary, priorities with links and next actions, category counts, and an AI-assistance notice.

Excerpt from the [saved real CPython run](examples/sample_report.md):

```text
#160829: HAVE_PROTOTYPES macro should be restored
Urgency: high
URL: https://github.com/python/cpython/issues/160829
Next action: Restore the HAVE_PROTOTYPES macro to avoid impacting
             third-party package builds.
```

A model suggestion, not a verified fix.

## How It Works

GitHub issues → LLM analysis → validated priorities → report.

Python validates issue numbers and ranks by suggested urgency, priority labels, comments, then issue number. Counts generate the summary without another model call. See [design rationale](docs/THOUGHT_PROCESS.md) and [AI assistance disclosure](docs/AI_LOG.md).

## Design Choices & Limitations

- **Read-only GitHub access:** no posting, labeling, closing issues, or executing issue-supplied commands. Reports stay local.
- **Bounded work:** at most 15 analyzed issues, two GitHub pages, and 800 body characters per issue. One batch, with at most one invalid-output repair attempt. Token limits and request timeouts apply; cost varies by model.
- **Partial coverage:** sampling can miss older urgent issues. Requested cutoffs and observed timestamp ranges do not guarantee full coverage. No matches produce an empty report without an LLM call.
- **Human judgment required:** validation checks structure, not truth. The audit found incorrect summaries and debatable priorities. Suggestions are not authoritative severity determinations; tests do not establish immunity to prompt injection.
