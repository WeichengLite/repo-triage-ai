# repo-triage-ai

Foundation for a Monday morning briefing for maintainers of public GitHub
repositories. Fetch issues as JSON or add `--triage` for validated LLM guidance
ranked in Python. The briefing renderer remains reserved for future work.

Requires Python 3.10 or later.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
repo-triage pallets/flask --limit 15
pytest
```

Optionally export `GITHUB_TOKEN` in your shell for authenticated API requests.
See `.env.example`; `.env` files are not loaded automatically.

The CLI prints structured issue JSON. It requests open issues sorted by latest
update, filters pull requests, and returns up to 15 actual issues by default
(30 maximum). It reads at most two pages of 100 API entries, so repositories
dominated by pull requests may yield fewer issues. Bodies are capped at 800
characters. Requests have a 10-second timeout; API and network failures produce
a clean error and a nonzero exit status.

Export `LLM_MODEL` (default `openai/gpt-4o-mini`) and the selected provider's
credentials, such as `OPENAI_API_KEY`, then run:

```sh
repo-triage pallets/flask --triage --limit 15
```

Triage sends at most 15 issues in one request, with a 16,000-token input budget
(including schema overhead and a 256-token margin), a 4,096-token output cap,
and a 20-second timeout per call. Over-budget inputs are rejected. LiteLLM token
counts are estimates for providers without an exact local tokenizer. One retry
is allowed for invalid JSON/schema/issue-number output; provider errors are not
retried. Two attempts can therefore take roughly 40 seconds plus local work.

The provider uses strict JSON Schema when advertised, JSON mode otherwise when
available, and JSON-only instructions as the final fallback. String and numeric
bounds are enforced locally because provider schema support varies. Models
without an advertised output-token limit are rejected. Refusals, truncated
responses, and repeated validation failures raise errors; no fallback triage is
fabricated. Structural validation cannot prove that a rationale is factually
correct. Issue content is untrusted data; no tools or command execution are
exposed to the model.

Python sorts by urgency, then the presence of an exact priority label
(`critical`, `high priority`, `priority: high`, `p0`, `p1`, case insensitive),
then descending comment count, then ascending issue number. Labels and comments
only break urgency ties.

Run the optional live default-model behavior test with `OPENAI_API_KEY` exported:

```sh
RUN_LIVE_LLM_TEST=1 pytest -q tests/test_llm_client.py -k live_default
```

This makes a small paid request to the default model and checks crash/feature
classification, concrete actions, and resistance to a sample prompt injection.
