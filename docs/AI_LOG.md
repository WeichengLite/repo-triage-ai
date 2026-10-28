# AI assistance log

- **Codex assistance:** Codex implemented the package, GitHub and LiteLLM clients,
  CLI, reporting, tests, and these documents through iterative user requests.
  It also debugged `.env` loading, added safe error handling and retry bounds,
  and executed local tests and live verification commands.
- **Human decisions:** The human specified the six-module architecture,
  dependencies, bounded single-batch triage, deterministic Python ranking,
  and exclusions such as agent frameworks and automatic GitHub writes. They
  directed the staged implementation, requested live checks and security review,
  and configured provider credentials locally. No additional human architectural
  overrides are claimed.
- **Verification performed:** The latest test check reported 119 passed and one
  optional live test skipped. A fresh Python 3.11 installation, imports, CLI help,
  and tests were checked without copied credentials; Ruff checks also passed.
  Separate real GitHub/LLM runs succeeded, including
  a 10-issue CPython run with one completion. Its report was compared with the
  captured validated results; all ten source issues were reviewed against the
  newest-first baseline. Secret scans and mocked error/injection tests were run.
  Semantic errors were documented; no benchmark accuracy or manipulation
  resistance was established.
