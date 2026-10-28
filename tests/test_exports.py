"""Tests for optional Word output, canonical content, and safe export names."""

import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from repo_triage.cli import main
from repo_triage.models import Issue, IssueTriage
from repo_triage.reporter import ExportError, build_digest, export_digest


@pytest.fixture
def timestamp() -> datetime:
    """Use a date whose local date differs from UTC."""
    return datetime.fromisoformat("2026-10-29T00:30:45+09:00")


def test_markdown_filename_uses_utc_date_and_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    monkeypatch.chdir(tmp_path)
    paths = export_digest("# Example\n", "pallets/flask", timestamp)
    assert paths == [Path("reports/flask_triage_2026-10-28.md")]
    assert paths[0].read_text() == "# Example\n"


def test_collisions_add_utc_time_without_overwriting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    monkeypatch.chdir(tmp_path)
    first = export_digest("first", "pallets/flask", timestamp)[0]
    second = export_digest("second", "pallets/flask", timestamp)[0]
    third = export_digest("third", "pallets/flask", timestamp)[0]
    assert second.name == "flask_triage_2026-10-28_153045.md"
    assert third.name == "flask_triage_2026-10-28_153045_2.md"
    assert first.read_text() == "first"
    assert second.read_text() == "second"
    assert third.read_text() == "third"


@pytest.mark.parametrize(
    "repository",
    [
        "../../etc/passwd",
        r"owner/..\..\evil",
        "owner/...",
        "owner/a:b?c*",
    ],
)
def test_filename_stays_inside_reports(
    repository: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = export_digest("example", repository, timestamp)[0]
    assert path.resolve().parent == (tmp_path / "reports").resolve()
    assert re.fullmatch(r"[A-Za-z0-9_.-]+_triage_2026-10-28\.md", path.name)


@pytest.mark.parametrize("output_format", ["docx", "both"])
def test_word_matches_canonical_report_and_has_clickable_links(
    output_format: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    pytest.importorskip("docx")
    monkeypatch.chdir(tmp_path)
    issue = Issue(
        number=101,
        title="Crash [on startup] & recovery",
        body="Crash.",
        labels=["bug"],
        comment_count=12,
        updated_at=datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
        html_url="https://github.com/example/repo/issues/101",
    )
    result = IssueTriage(
        issue_number=101,
        category="bug",
        urgency="high",
        summary="Reported crash.",
        rationale="Startup is blocked.",
        next_action="Reproduce the startup crash.",
    )
    digest = build_digest(
        "example/repo",
        [issue],
        [result],
        generated_at=timestamp,
        since=datetime(2026, 10, 21, tzinfo=timezone.utc),
        limit_reason="issue_limit",
    )
    with patch("litellm.completion") as complete:
        paths = export_digest(digest, "example/repo", timestamp, output_format)
    complete.assert_not_called()
    assert len({path.stem for path in paths}) == 1
    word = next(path for path in paths if path.suffix == ".docx")
    with ZipFile(word) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
        relationships = ET.fromstring(
            archive.read("word/_rels/document.xml.rels")
        )
    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    paragraphs = [
        "".join(p.itertext())
        for p in document.findall(".//w:body/w:p", namespace)
    ]
    expected = []
    for line in digest.splitlines():
        if line:
            plain = re.sub(r"^#{1,3} |^- ", "", line)
            if plain.startswith("**") and plain.endswith("**"):
                plain = plain[2:-2]
            expected.append(
                html.unescape(
                    re.sub(r"\\([\\`*_{}\[\]()#+.!|>-])", r"\1", plain)
                )
            )
    assert paragraphs == expected
    targets = {entry.attrib.get("Target") for entry in relationships}
    assert str(issue.html_url) in targets
    assert "https://github.com/example/repo" in targets
    if output_format == "both":
        markdown = next(path for path in paths if path.suffix == ".md")
        assert markdown.read_text(encoding="utf-8") == digest


def test_missing_word_dependency_fails_before_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["repo-triage", "example/repo", "--export", "--format", "both"],
    )
    with (
        patch.dict(sys.modules, {"docx": None}),
        patch("requests.get") as get,
        patch("litellm.completion") as complete,
    ):
        assert main() == 1
    get.assert_not_called()
    complete.assert_not_called()
    assert ".[word]" in capsys.readouterr().err
    assert not (tmp_path / "reports").exists()


def test_markdown_remains_usable_without_word_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch.dict(sys.modules, {"docx": None}):
        assert export_digest("example", "owner/repo", timestamp)[0].exists()


def test_format_without_export_keeps_terminal_only_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["repo-triage", "example/repo", "--format", "docx"]
    )
    with (
        patch.dict(sys.modules, {"docx": None}),
        patch(
            "repo_triage.cli.GitHubClient.fetch_open_issues", return_value=[]
        ),
    ):
        assert main() == 0
    assert not (tmp_path / "reports").exists()


def test_partial_exports_are_removed_after_filesystem_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    pytest.importorskip("docx")
    monkeypatch.chdir(tmp_path)
    original = Path.open

    def fail_word(path: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if path.suffix == ".docx":
            raise PermissionError("synthetic-private-value")
        return original(path, *args, **kwargs)

    with patch("pathlib.Path.open", new=fail_word):
        with pytest.raises(ExportError) as caught:
            export_digest("example", "owner/repo", timestamp, "both")
    assert "synthetic-private-value" not in str(caught.value)
    assert list((tmp_path / "reports").iterdir()) == []


def test_both_exports_share_collision_suffix_and_preserve_existing_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: datetime,
) -> None:
    pytest.importorskip("docx")
    monkeypatch.chdir(tmp_path)
    original = export_digest("original", "owner/my.repo", timestamp)[0]
    assert original.name == "my.repo_triage_2026-10-28.md"
    paths = export_digest("new report", "owner/my.repo", timestamp, "both")
    assert {path.stem for path in paths} == {"my.repo_triage_2026-10-28_153045"}
    assert {path.suffix for path in paths} == {".md", ".docx"}
    assert original.read_text() == "original"


def test_naive_generation_time_is_rejected_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="timezone"):
        export_digest("example", "owner/repo", datetime(2026, 10, 28))
    assert not (tmp_path / "reports").exists()


def test_invalid_cli_format_is_rejected_before_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["repo-triage", "owner/repo", "--export", "--format", "pdf"],
    )
    with patch("requests.get") as get:
        with pytest.raises(SystemExit) as error:
            main()
    assert error.value.code == 2
    get.assert_not_called()
