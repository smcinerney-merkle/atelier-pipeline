"""Structural test: `.cursor-plugin/agents/` must be an exact assembly of
`source/shared/agents/` bodies with the Cursor config-time placeholders
resolved.

Background: `/pipeline-setup` (and any future update path) never
regenerates this fork's own `.cursor-plugin/agents/` -- that tree is
committed output, not a live install target. Nothing mechanically keeps it
in sync with `source/shared/agents/` when a shared body changes. This test
is the only guard against drift; without it, `.cursor-plugin/agents/` goes
stale silently (as it did for 12 of 14 agents before this fix -- see
`docs/pipeline/last-build-cursor-resync.md`).

Assembly rule (operator decision, 2026-09-24): `.cursor-plugin/` is the
Cursor plugin **as shipped to every installing project** -- it is not this
fork's own installed copy the way `.claude/` is. A placeholder resolved at
assembly time to *this project's own* config value (e.g. this repo's
CLAUDE.md lint/typecheck commands) would ship that value to every Cursor
user regardless of their own project's lint/typecheck setup. Only
placeholders that resolve to a **platform path** -- fixed by which IDE
plugin this is, not by which project installs it -- are safe to bake in:

- The Cursor `.md` file carries NO YAML frontmatter -- frontmatter lives
  only in `source/cursor/agents/<name>.frontmatter.yml`, which Cursor's
  runtime consumes separately (see ADR references in
  `skills/pipeline-setup/hooks.md`). The `.md` body is the shared content,
  verbatim, with exactly two config-time placeholders resolved:
    - `{config_dir}`          -> `.cursor`
    - `{pipeline_state_dir}`  -> `docs/pipeline`
  Confirmed against the two agents (`scout`, `synthesis`) whose Cursor
  copies already matched their shared bodies byte-for-byte (neither
  contains any `{...}` placeholder, so they only confirm "no frontmatter
  prepended").
- `{lint_command}` and `{typecheck_command}` stay literal in the Cursor
  copy, exactly as they do in every `.claude/agents/*.md` copy and in
  `{test_command}` everywhere. They are per-installing-project config, not
  platform paths -- resolving them at assembly time would bake this fork's
  own `CLAUDE.md` Test Commands values (`echo "no linter configured"` /
  `echo "no typecheck configured"`) into every downstream Cursor install,
  silently disabling their real lint/typecheck gate. `colby.md` line 51
  had exactly this bug prior to this fix cycle.
- Every other placeholder ({feature}, {slug}, {path}, {paths}, {thing},
  {adr_dir}, {test_command}, {Title}, ...) is a runtime slot filled in by
  the agent at invocation time, not by assembly, and MUST stay literal in
  both the shared source and the Cursor copy.

Every agent under `source/shared/agents/` must have a corresponding
`.cursor-plugin/agents/<name>.md`, and vice versa -- no missing, no extra.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import CURSOR_AGENTS, SHARED_AGENTS


# Config-time placeholders resolved during Cursor assembly -- platform
# paths ONLY (fixed by the Cursor plugin itself, not by whichever project
# installs it). {lint_command}/{typecheck_command} are per-installing-
# project config and MUST stay literal, same as {test_command} and every
# .claude/agents/ copy. Order does not matter -- neither substitution value
# contains the other key's braces.
CURSOR_PLACEHOLDER_RESOLUTIONS = {
    "{config_dir}": ".cursor",
    "{pipeline_state_dir}": "docs/pipeline",
}


def _expected_cursor_body(shared_text: str) -> str:
    """Apply the Cursor assembly rule to a shared agent body."""
    expected = shared_text
    for placeholder, value in CURSOR_PLACEHOLDER_RESOLUTIONS.items():
        expected = expected.replace(placeholder, value)
    return expected


def _shared_agent_names() -> list[str]:
    return sorted(p.stem for p in SHARED_AGENTS.glob("*.md"))


SHARED_AGENT_NAMES = _shared_agent_names()


def test_shared_agents_discovered() -> None:
    """Sanity: the source tree isn't empty, so the parametrized tests below
    aren't vacuously trivial."""
    assert SHARED_AGENT_NAMES, (
        f"No agent .md files found under {SHARED_AGENTS}; "
        "the parity test would otherwise pass vacuously."
    )


def test_no_missing_cursor_copies() -> None:
    """Every shared agent must have a Cursor mirror -- no silent omissions."""
    cursor_names = {p.stem for p in CURSOR_AGENTS.glob("*.md")}
    missing = set(SHARED_AGENT_NAMES) - cursor_names
    assert not missing, (
        f"Missing .cursor-plugin/agents/ copies for: {sorted(missing)}. "
        "Every agent under source/shared/agents/ needs a Cursor mirror."
    )


def test_no_extra_cursor_copies() -> None:
    """No orphan Cursor agent files with no shared-body source."""
    cursor_names = {p.stem for p in CURSOR_AGENTS.glob("*.md")}
    extra = cursor_names - set(SHARED_AGENT_NAMES)
    assert not extra, (
        f"Extra .cursor-plugin/agents/ copies with no source/shared/agents/ "
        f"counterpart: {sorted(extra)}. Remove the orphan or add the "
        "missing shared source."
    )


@pytest.mark.parametrize("name", SHARED_AGENT_NAMES)
def test_cursor_agent_matches_assembled_shared_body(name: str) -> None:
    """`.cursor-plugin/agents/<name>.md` must equal the shared body with
    only the two platform-path placeholders resolved -- byte for byte."""
    shared_path = SHARED_AGENTS / f"{name}.md"
    cursor_path = CURSOR_AGENTS / f"{name}.md"

    assert cursor_path.exists(), (
        f"{cursor_path} does not exist. Every agent in source/shared/agents/ "
        "needs an assembled .cursor-plugin/agents/ mirror."
    )

    shared_text = shared_path.read_text(encoding="utf-8")
    expected = _expected_cursor_body(shared_text)
    actual = cursor_path.read_text(encoding="utf-8")

    assert actual == expected, (
        f"{cursor_path} has drifted from source/shared/agents/{name}.md. "
        "Regenerate it from the shared body using the Cursor assembly rule "
        "(resolve {config_dir} and {pipeline_state_dir} only -- both are "
        "platform paths fixed by the Cursor plugin itself; leave "
        "{lint_command}, {typecheck_command}, and every other placeholder "
        "literal, since those are per-installing-project config that must "
        "not be baked into the shipped plugin). Do not hand-edit the "
        "Cursor copy directly -- the shared body is the source of truth."
    )


@pytest.mark.parametrize("name", SHARED_AGENT_NAMES)
def test_shared_body_claims_no_path_guard_enforcement(name: str) -> None:
    """Shared bodies are platform-neutral: they state the write contract
    but must not claim a guard enforces it. The Claude Code and Cursor
    guards differ, so any such claim is false on at least one platform.
    Matches across line breaks (colby.md wraps between the two words)."""
    text = (SHARED_AGENTS / f"{name}.md").read_text(encoding="utf-8")
    assert not re.search(r"path\s+guard\s+blocks", text, re.I), (
        f"source/shared/agents/{name}.md claims platform-specific "
        "enforcement ('path guard blocks'). Keep the contract, drop the claim."
    )
