"""Integration tests for scripts/merge-pipeline-config.sh.

Verifies the pipeline-config.json missing-key merge (G-151 note item 8,
operator decision 2026-09-25): only template keys the installed file lacks
get added, existing keys are never touched, `agent_roster` is never added,
and malformed JSON is left byte-identical. Tests run the real script via
subprocess against fixture files staged in tmp_path, so we exercise the
actual jq merge logic, not a restatement of it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MERGE_SCRIPT = PROJECT_ROOT / "scripts" / "merge-pipeline-config.sh"

TEMPLATE_BODY = {
    "project_name": "",
    "git_available": True,
    "brevity": True,
    "conversation_language": "en",
    "artifact_language": "en",
    "language_grade_level": 9,
    "agent_roster": {
        "robert": {"enabled": True, "firing": "core"},
        "sarah": {"enabled": True, "firing": "core"},
    },
    "generic_commit_enabled": True,
}


def _run_merge(template: Path, installed: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(MERGE_SCRIPT), str(template), str(installed)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _stage(tmp_path: Path, template_body: dict, installed_body: dict) -> tuple[Path, Path]:
    template = tmp_path / "template.json"
    installed = tmp_path / "installed.json"
    template.write_text(json.dumps(template_body, indent=2) + "\n")
    installed.write_text(json.dumps(installed_body, indent=2) + "\n")
    return template, installed


def test_existing_key_with_non_template_value_left_unchanged(tmp_path: Path) -> None:
    """An installed key survives untouched even when its value differs from
    the template (and even when the template's own value is empty/default)."""
    installed_body = {"project_name": "real-project-name", "git_available": False}
    template, installed = _stage(tmp_path, TEMPLATE_BODY, installed_body)

    result = _run_merge(template, installed)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    merged = json.loads(installed.read_text())
    assert merged["project_name"] == "real-project-name"
    assert merged["git_available"] is False


def test_missing_key_added_with_template_value(tmp_path: Path) -> None:
    installed_body = {"project_name": "real-project-name", "git_available": False}
    template, installed = _stage(tmp_path, TEMPLATE_BODY, installed_body)

    result = _run_merge(template, installed)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    merged = json.loads(installed.read_text())
    assert merged["brevity"] is True
    assert merged["conversation_language"] == "en"
    assert merged["artifact_language"] == "en"
    assert merged["language_grade_level"] == 9
    assert merged["generic_commit_enabled"] is True
    assert "brevity" in result.stdout
    assert "conversation_language" in result.stdout
    assert "artifact_language" in result.stdout
    assert "language_grade_level" in result.stdout


def test_agent_roster_absent_from_installed_stays_absent(tmp_path: Path) -> None:
    """agent_roster is the ADR-0060 signal for the Step 1f roster questions --
    it must never be introduced by this merge, even though the template has it
    and the installed file lacks it entirely."""
    installed_body = {"project_name": "real-project-name"}
    template, installed = _stage(tmp_path, TEMPLATE_BODY, installed_body)

    result = _run_merge(template, installed)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    merged = json.loads(installed.read_text())
    assert "agent_roster" not in merged
    assert "agent_roster" not in result.stdout


def test_malformed_json_left_byte_identical(tmp_path: Path) -> None:
    template = tmp_path / "template.json"
    installed = tmp_path / "installed.json"
    template.write_text(json.dumps(TEMPLATE_BODY, indent=2) + "\n")
    malformed = '{ "project_name": "x", invalid json here'
    installed.write_text(malformed)

    result = _run_merge(template, installed)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert installed.read_text() == malformed, "malformed installed file must be byte-identical after the merge attempt"
    combined = (result.stdout + result.stderr).lower()
    assert "not valid json" in combined
    assert "warning" in combined


def test_no_missing_keys_reports_none_added(tmp_path: Path) -> None:
    template_body = {"a": 1, "agent_roster": {"x": 1}}
    installed_body = {"a": 99}
    template, installed = _stage(tmp_path, template_body, installed_body)

    result = _run_merge(template, installed)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    merged = json.loads(installed.read_text())
    assert merged == {"a": 99}
    assert "no keys added" in result.stdout


def test_missing_installed_file_errors_without_creating_one(tmp_path: Path) -> None:
    """This script only merges into an EXISTING file -- a fresh install is the
    setup skill's plain copy-the-template path, not this script's job."""
    template = tmp_path / "template.json"
    template.write_text(json.dumps(TEMPLATE_BODY, indent=2) + "\n")
    installed = tmp_path / "installed.json"

    result = _run_merge(template, installed)

    assert result.returncode != 0
    assert not installed.exists()


def test_missing_args_rejected(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(MERGE_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
