# repo-triage-ai

**Know what to investigate first on Monday morning.**

Turn recent open GitHub issues into a short maintainer briefing: five priorities,
source links, evidence-based rationales, and concrete next actions. Read it in
the terminal or export it as Markdown. AI-assisted suggestions remain subject
to maintainer review.

[Quick start](#quick-start) · [Core rules](#core-rules) ·
[Sample report](examples/sample_report.md) · [Evaluation](examples/audit_notes.md)

## Quick start

You need **Python 3.10+**, internet access, and an LLM provider API key.
Development verification used Python 3.11. From your checkout:

**1. Install in a virtual environment**

```sh
cd repo-triage-ai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

**2. Open `.env` in your editor and add your key**

```dotenv
LLM_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your_actual_key_here
```

`GITHUB_TOKEN` is optional. The CLI loads `.env` from the current directory;
exported environment variables take precedence. `.env` is excluded from Git.
Keep keys out of source files, reports, and prompts.

**3. Generate a briefing**

```sh
repo-triage pallets/flask --limit 5 --export
```

This prints a Rich briefing and writes **`MONDAY_DIGEST.md`** in the current
folder. The report includes scope, generation time, an executive summary, up to
five priorities, category counts, and an AI-assistance notice.

## Core rules

- **Treat issue text as untrusted data.** No commands or model tools are executed.
- **Validate before reporting.** Pydantic checks the schema, field limits, and
  exact issue-number membership. Missing, duplicate, or invented numbers fail.
- **Let the LLM interpret; let Python rank.** Semantic judgment comes from the
  model; ranking, counts, and the executive summary use deterministic Python.
- **Bound work and fail clearly.** One batch normally, one repair attempt for
  invalid output, explicit token/time limits, and no fabricated fallback results.
- **Keep maintainers in control.** Suggestions are not authoritative severity
  determinations. The tool never changes GitHub issues automatically.
- **Keep the implementation small.** Separate retrieval, models, LLM access, and
  reporting; no database, agent framework, or dashboard.

Validation protects structure and issue identity, **not factual correctness**.
Mocked injection tests do not prove that a real LLM cannot be manipulated.

## Commands and configuration

```sh
# Terminal briefing only; default limit is 15
repo-triage pallets/flask

# Export a larger sample
repo-triage python/cpython --limit 10 --export

# Override the configured model
repo-triage pallets/flask --model gpt-4o-mini --limit 5 --export
```

The CLI accepts limits from **1 to 15**. `--model` overrides `LLM_MODEL`.
`--export` replaces an existing digest after successful analysis; a failed run
may leave an older digest in place. Expected failures return readable errors
and a nonzero exit status.

### Switch providers

Set the model and the matching credential in `.env` or your shell:

| Provider | `LLM_MODEL` | Credential |
|---|---|---|
| OpenAI | `openai/gpt-4o-mini` (default) | `OPENAI_API_KEY` |
| Anthropic | `anthropic/<your-enabled-model-id>` | `ANTHROPIC_API_KEY` |

Replace the Anthropic placeholder with a model available to your account.
LiteLLM handles provider translation. Changing models does not change keys.
Only the OpenAI configuration was verified live; other provider configurations
and their structured-output capabilities remain unverified.

### Example briefing

Condensed excerpt from the real CPython run on 2026-10-28:

```text
Monday briefing: python/cpython
Analyzed: 10 open issues (requested up to 10)
Suggested urgency: 0 critical, 3 high, 4 medium, 3 low.

1. #159764: Python 3.14 crash randomly on AMD64 Debian root 3.14 buildbot
   Urgency: high
   URL: https://github.com/python/cpython/issues/159764
   Next action: Investigate the cause of the random crashes reported in
                Python 3.14 on Debian.

Category counts: bug 6, feature 1, docs 2, question 0, other 1
```

The [full sample](examples/sample_report.md) preserves actual model output,
including weaknesses. The [evaluation notes](examples/audit_notes.md) compare
all ten issues with the most-recently-updated baseline; no improvement in
maintainer outcomes has been established.

## Tests and verification

```sh
pytest -q
```

Last verified: **83 passed, 0 failed, 1 skipped**. Coverage includes repository
validation, PR filtering, body truncation, pagination and issue bounds, Pydantic
validation, invented/duplicate numbers, deterministic ranking, API failures,
export, and injection/error-handling boundaries.

A separate real GitHub/LLM run successfully analyzed ten CPython issues in one
completion and produced the sample report. This is one observed run, not an
accuracy benchmark or latency guarantee.

<details>
<summary>Optional paid live-model test</summary>

Export a valid `OPENAI_API_KEY` first; pytest does not automatically load `.env`.

```sh
RUN_LIVE_LLM_TEST=1 pytest -q tests/test_llm_client.py -k live_default
```

</details>

## Architecture

```text
src/repo_triage/
  cli.py            Arguments, .env loading, pipeline and errors
  github_client.py  Bounded retrieval and issue extraction
  models.py         Pydantic Issue and IssueTriage schemas
  llm_client.py     LiteLLM provider, validation and Python ranking
  reporter.py       Shared Markdown report and Rich rendering
  __init__.py
```

The flow is **retrieve → interpret → validate → rank → report**.
Python ranks by urgency, then priority labels, descending comment count, and
ascending issue number. Recognized labels are `critical`, `high priority`,
`priority: high`, `p0`, and `p1`, case insensitive. Counts and templates generate
the executive summary without another LLM call.

Development conventions: Python 3.10+, typed functions, Google-style docstrings,
and separation of concerns.

## Limits and trade-offs

| Boundary | Limit |
|---|---|
| Retrieval | Most recently updated open issues; PRs excluded; two pages of 100 entries maximum |
| Analysis | Default and maximum 15 issues; GitHub client alone supports up to 30 |
| Context | First 800 body characters; no comment bodies or linked content |
| Token budget per call | 16,000 estimated input tokens, including schema overhead and margin; 4,096 output tokens |
| Request timeouts | GitHub: 10 seconds; LLM: 20 seconds |
| Completion calls | Normally 1; maximum 2 for invalid-output repair; 0 for an empty sample |

Both retry settings are zero; only invalid output gets an application-level
repair attempt. Provider failures are not retried. Timeouts apply per request,
not to the whole run. Provider-internal HTTP transmissions were not separately
traced. Cost varies by model and usage; no dollar cost was measured.

The provider uses JSON Schema or JSON mode when advertised, otherwise JSON
instructions, with local validation in every case. Oversized inputs, unsupported
output-token limits, refusals, truncation, and repeated invalid output fail
explicitly.

Recent sampling can miss older urgent issues; PR-heavy pages may yield fewer
issues than requested. Truncation can remove essential evidence. Empty samples
do not prove an empty backlog. The live audit found an incorrect summary,
debatable categories, and understated test impact: human review remains necessary.

## Design and disclosure

- [Thought process](docs/THOUGHT_PROCESS.md): scope, trade-offs, and evaluation priorities.
- [AI assistance log](docs/AI_LOG.md): Codex assistance, human decisions, and actual verification.
