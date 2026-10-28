"""Run one live two-issue smoke test using exported provider credentials."""

import contextlib
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch


def main() -> int:
    """Run real triage, validate before printing, and return a shell status."""
    started = time.perf_counter()
    calls = 0
    diagnostics: dict[str, object] = {
        "error_category": "unknown",
        "provider": "unknown",
        "model": "unknown",
        "required_api_key_present": False,
        "configuration_loading_succeeded": False,
        "dotenv_loaded": False,
    }
    previous_logging_level = logging.root.manager.disable
    try:
        # SDK diagnostics can include request data: never forward them.
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            # python-dotenv is already installed as a LiteLLM dependency.
            from dotenv import load_dotenv

            diagnostics["dotenv_loaded"] = load_dotenv(
                Path(__file__).resolve().parents[1] / ".env", override=False
            )
            diagnostics["configuration_loading_succeeded"] = True
            os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
            import litellm

            from repo_triage.llm_client import LiteLLMProvider, TriageClient
            from repo_triage.models import Issue, IssueTriage

            litellm.suppress_debug_info = True
            provider = LiteLLMProvider()
            # Accept model identifiers, but never print URLs or key material.
            if (
                re.fullmatch(r"[A-Za-z0-9_./:-]+", provider.model)
                and "://" not in provider.model
            ):
                diagnostics["model"] = provider.model
            _, provider_name, _, _ = litellm.get_llm_provider(
                model=provider.model
            )
            diagnostics["provider"] = provider_name
            key_names = {
                "openai": ("OPENAI_API_KEY",),
                "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
                "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
                "azure": ("AZURE_API_KEY",),
            }.get(provider_name, (f"{provider_name.upper()}_API_KEY",))
            diagnostics["required_api_key_present"] = any(
                bool(os.getenv(name, "").strip()) for name in key_names
            )
            now = datetime.now(timezone.utc)
            issues = [
                Issue(
                    number=101,
                    title=("Application crashes when loading configuration "
                           "after latest release"),
                    body=("Multiple users report the application crashes "
                          "immediately after upgrading. This blocks "
                          "application startup."),
                    labels=["bug"], comment_count=12, updated_at=now,
                    html_url="https://github.com/example/synthetic/issues/101",
                ),
                Issue(
                    number=102,
                    title="Request to change documentation heading color",
                    body=("A suggestion to improve the appearance of a "
                          "documentation page. No functional issue."),
                    labels=["enhancement"], comment_count=0, updated_at=now,
                    html_url="https://github.com/example/synthetic/issues/102",
                ),
            ]
            # wraps forwards every call to the REAL SDK; no fake responses.
            with patch("litellm.completion", wraps=litellm.completion) as live:
                try:
                    results = TriageClient(provider).triage(issues)
                finally:
                    calls = live.call_count
            validated = [
                IssueTriage.model_validate_json(item.model_dump_json())
                for item in results
            ]
            numbers = [item.issue_number for item in validated]
            if sorted(numbers) != [101, 102]:
                raise ValueError("Missing, duplicate, or invented issue number.")
            if numbers != [101, 102]:
                raise ValueError("Issue 101 was not ranked above issue 102.")
            output = json.dumps({
                "issues": [
                    {
                        "Issue number": item.issue_number,
                        "Category": item.category,
                        "Urgency": item.urgency,
                        "Summary": item.summary,
                        "Rationale": item.rationale,
                        "Recommended next action": item.next_action,
                    }
                    for item in validated
                ],
                "Number of LLM calls": calls,
                "Runtime in seconds": round(time.perf_counter() - started, 3),
            }, indent=2)
            secrets = [
                value for name, value in os.environ.items()
                if value and any(part in name.upper() for part in (
                    "API_KEY", "TOKEN", "SECRET", "PASSWORD", "ACCESS_KEY"
                ))
            ]
            # Check decoded values as well as serialized output for escaping.
            text = output + "\n" + "\n".join(
                item.summary + "\n" + item.rationale + "\n" + item.next_action
                for item in validated
            )
            if any(secret in text for secret in secrets):
                raise ValueError("Credential-like environment value in output.")
    except Exception as error:
        # Do not expose exception messages, SDK logs, or unvalidated output.
        category = getattr(error, "category", "unknown")
        if category in {
            "authentication", "model_not_found", "unsupported_response_format",
            "rate_limit", "connectivity", "unknown",
        }:
            diagnostics["error_category"] = category
        print(json.dumps(diagnostics))
        print(json.dumps({
            "Number of LLM calls": calls,
            "Runtime in seconds": round(time.perf_counter() - started, 3),
        }))
        return 1
    finally:
        logging.disable(previous_logging_level)
    diagnostics.pop("error_category")
    print(json.dumps(diagnostics))
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
