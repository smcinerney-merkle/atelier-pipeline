"""Structural test: investigator and sherlock archive their output, append-only.

FORK DEVIATION (smcinerney-merkle/atelier-pipeline), ported from friction
2026-09-22. Upstream has both agents overwrite a single slot
(`last-qa-report.md`, `last-case-file.md`), so every run destroys the previous
report and it survives only if someone happened to commit it. Friction lost
track of occupants that way several times in one day.

Here each run writes a NEW uniquely named file into an archive directory,
refusing to overwrite (`set -C` for investigator), and only then copies it to
the `last-*` slot the rest of the pipeline reads. The slot stays, so nothing
downstream changes.

This test is the guard the friction session asked for in prose ("after any
upgrade, check that investigator.md still writes to qa-reports/"): an upstream
merge that reverts either edit turns it red. It checks both the shared source
that setup assembles from and the plugin's assembled `.claude/agents/` copy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COPIES = ("source/shared/agents", ".claude/agents")


def _output_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start, end = text.find("<output>"), text.find("</output>")
    assert start != -1 and end > start, f"{path}: no <output> block"
    return text[start:end]


@pytest.mark.parametrize("copy", COPIES)
def test_investigator_archives_to_qa_reports(copy: str) -> None:
    out = _output_block(REPO_ROOT / copy / "investigator.md")
    assert 'f="docs/pipeline/qa-reports/' in out, "no uniquely named archive file"
    assert "set -C" in out, "archive write no longer refuses to overwrite"
    assert 'cat > "$f"' in out, "report is not written to the archive file"
    assert 'cp "$f" docs/pipeline/last-qa-report.md' in out, "slot copy missing"
    assert "cat > docs/pipeline/last-qa-report.md" not in out, (
        "upstream's single-slot overwrite is back"
    )


@pytest.mark.parametrize("copy", COPIES)
def test_sherlock_archives_to_case_files(copy: str) -> None:
    text = (REPO_ROOT / copy / "sherlock.md").read_text(encoding="utf-8")
    assert "{pipeline_state_dir}/case-files/<UTC timestamp>.md" in text
    assert "never\noverwrite an existing one" in text or \
        "never overwrite an existing one" in text
    assert "Overwrite the prior file" not in text, (
        "upstream's single-slot overwrite is back"
    )
