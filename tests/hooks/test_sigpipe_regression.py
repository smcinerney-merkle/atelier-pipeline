"""Regression tests for the SIGPIPE boot-corruption defect (G-147 item A).

hook_lib_pipeline_status_field breaks out of its read loop at the first
PIPELINE_STATUS marker (the active entry is always first in
pipeline-state.md). Piping a large file into it via `cat FILE | function`
leaves cat's stdout open when the function returns early -- cat takes
SIGPIPE (exit 141), and under `set -o pipefail` the caller's `|| echo
"idle"` fires *alongside* the real value, producing a corrupted field
(e.g. "build\nidle"). The fix is to use a stdin redirect
(`function < FILE`) everywhere instead of a pipe.

This file proves:
  1. The bug reproduces on the pre-fix session-boot.sh (git rev 9aa2cd1)
     against a >700KB state file.
  2. The current (fixed) session-boot.sh returns a clean, single-valued
     phase field against the same fixture.
  3. No hook anywhere in the source or installed trees feeds the function
     via a `cat | function` pipe (comments excluded).
  4. Mutating a fixed copy back to the pipe form is caught by check #3
     (kills the guard -- proves it is load-bearing).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import PROJECT_ROOT

CLAUDE_HOOKS_DIR = PROJECT_ROOT / "source" / "claude" / "hooks"
SHARED_HOOKS_DIR = PROJECT_ROOT / "source" / "shared" / "hooks"

# Trees to scan for the structural guard (test #3). Each is a directory
# containing hook scripts; comments are stripped before matching so the
# CORRECT/BROKEN teaching example in hook-lib.sh's own header does not
# trip the check.
SCAN_TREES = [
    PROJECT_ROOT / "source" / "shared" / "hooks",
    PROJECT_ROOT / "source" / "claude" / "hooks",
    PROJECT_ROOT / "source" / "cursor" / "hooks",
    PROJECT_ROOT / ".claude" / "hooks",
    PROJECT_ROOT / ".cursor-plugin" / "hooks",
]


def _build_large_state_file(tmp_path: Path) -> Path:
    """Build a >700KB pipeline-state.md.

    First PIPELINE_STATUS marker: phase=build, feature=sigpipe-fixture.
    Followed by enough later markers with phase=idle to exceed 700KB, so
    the function's early break (after the first marker) leaves a large
    amount of unread stdin behind -- the exact condition that triggers
    SIGPIPE on a piped cat.
    """
    state_dir = tmp_path / "docs" / "pipeline"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "pipeline-state.md"

    lines = ["# Pipeline State", ""]
    lines.append(
        '<!-- PIPELINE_STATUS: {"phase":"build","feature":"sigpipe-fixture"} -->'
    )
    # Pad past 700KB with later idle markers + filler text.
    filler_line = (
        "Filler line to grow the file past 700KB. " * 8
        + '<!-- PIPELINE_STATUS: {"phase":"idle","feature":""} -->'
    )
    total_size = sum(len(l) + 1 for l in lines)
    while total_size < 720_000:
        lines.append(filler_line)
        total_size += len(filler_line) + 1

    state_file.write_text("\n".join(lines) + "\n")
    assert state_file.stat().st_size > 700_000, (
        f"Fixture is only {state_file.stat().st_size} bytes; need >700000"
    )
    return state_file


def _run_session_boot(script_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run session-boot.sh from script_dir with cwd=tmp_path.

    env -u ATELIER_SETUP_MODE per the session warning; also strips
    CLAUDE_PROJECT_DIR/CURSOR_PROJECT_DIR so session_state_dir() falls
    back to the relative "docs/pipeline" path, which resolves under
    cwd=tmp_path to where _build_large_state_file wrote the fixture.
    """
    env = os.environ.copy()
    env.pop("ATELIER_SETUP_MODE", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CURSOR_PROJECT_DIR", None)
    return subprocess.run(
        ["bash", str(script_dir / "session-boot.sh")],
        input="",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=30,
    )


def _prepare_hook_dir(tmp_path: Path, session_boot_content: str, hook_lib_content: str) -> Path:
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "session-boot.sh").write_text(session_boot_content)
    (hooks_dir / "hook-lib.sh").write_text(hook_lib_content)
    return hooks_dir


# ═══════════════════════════════════════════════════════════════════════
# 1. Pre-fix session-boot.sh (git rev 9aa2cd1) corrupts phase on a >700KB
#    state file.
# ═══════════════════════════════════════════════════════════════════════


def test_unfixed_session_boot_corrupts_phase_on_large_state_file(tmp_path):
    old_session_boot = subprocess.run(
        ["git", "show", "9aa2cd1:source/claude/hooks/session-boot.sh"],
        cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, text=True, check=True,
    ).stdout
    # hook_lib_pipeline_status_field's own logic is unchanged by this fix
    # (only its docstring/comments changed) -- current hook-lib.sh is a
    # faithful stand-in for the function body at 9aa2cd1.
    current_hook_lib = (SHARED_HOOKS_DIR / "hook-lib.sh").read_text()

    _build_large_state_file(tmp_path)
    hooks_dir = _prepare_hook_dir(tmp_path, old_session_boot, current_hook_lib)

    r = _run_session_boot(hooks_dir, tmp_path)
    assert r.returncode == 0, f"session-boot.sh must always exit 0. Output: {r.stdout!r}"

    payload = json.loads(r.stdout)
    phase = payload["phase"]
    # This is the bug: SIGPIPE fires the `|| echo "idle"` fallback
    # *alongside* the real "build" value, so PHASE becomes "build\nidle"
    # (json_escape then encodes the embedded newline as \n).
    assert phase != "build", (
        f"Expected the PRE-FIX bug to reproduce (phase corrupted by SIGPIPE "
        f"fallback), but got a clean phase={phase!r}. If this assertion "
        f"fails, the reproduction fixture no longer triggers the SIGPIPE "
        f"condition and this test no longer proves anything."
    )
    assert "idle" in phase and "build" in phase, (
        f"Expected corrupted phase to contain both 'build' (the real value) "
        f"and 'idle' (the spurious fallback), got {phase!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 2. Fixed session-boot.sh returns a clean, single-valued phase.
# ═══════════════════════════════════════════════════════════════════════


def test_fixed_session_boot_returns_clean_phase_on_large_state_file(tmp_path):
    fixed_session_boot = (CLAUDE_HOOKS_DIR / "session-boot.sh").read_text()
    fixed_hook_lib = (SHARED_HOOKS_DIR / "hook-lib.sh").read_text()

    _build_large_state_file(tmp_path)
    hooks_dir = _prepare_hook_dir(tmp_path, fixed_session_boot, fixed_hook_lib)

    r = _run_session_boot(hooks_dir, tmp_path)
    assert r.returncode == 0, f"session-boot.sh must always exit 0. Output: {r.stdout!r}"

    payload = json.loads(r.stdout)
    phase = payload["phase"]
    feature = payload["feature"]

    assert phase == "build", (
        f"Expected phase == 'build' exactly, got {phase!r} "
        f"(repr for hidden chars: {repr(phase)})"
    )
    assert "\n" not in phase, f"phase must not contain a newline: {phase!r}"
    assert feature == "sigpipe-fixture", f"Expected feature == 'sigpipe-fixture', got {feature!r}"
    assert payload["pipeline_active"] is True


# ═══════════════════════════════════════════════════════════════════════
# 3. Structural guard: no hook anywhere feeds the function via a cat pipe.
# ═══════════════════════════════════════════════════════════════════════


def _strip_bash_comments(text: str) -> str:
    """Strip full-line and trailing `#` comments so documentation examples
    (e.g. hook-lib.sh's own CORRECT/BROKEN teaching block) do not trip the
    structural guard below."""
    out_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Trailing comment (naive: good enough, no '#' appears inside the
        # cat-pipe pattern's literal text in any real caller).
        if "#" in line:
            line = line.split("#", 1)[0]
        out_lines.append(line)
    return "\n".join(out_lines)


def _find_cat_pipe_violations(tree: Path) -> list[str]:
    violations = []
    if not tree.exists():
        return violations
    for path in sorted(tree.glob("*.sh")):
        code = _strip_bash_comments(path.read_text())
        for i, line in enumerate(code.splitlines(), start=1):
            if "hook_lib_pipeline_status_field" in line and "|" in line and "cat" in line:
                # Confirm it's actually `cat ... | hook_lib_pipeline_status_field`
                # (as opposed to e.g. piping the function's own output onward).
                idx = line.find("hook_lib_pipeline_status_field")
                before = line[:idx]
                if "cat" in before and "|" in before:
                    violations.append(f"{path}:{i}: {line.strip()}")
    return violations


@pytest.mark.parametrize("tree", SCAN_TREES, ids=[str(t) for t in SCAN_TREES])
def test_no_cat_pipe_into_pipeline_status_field(tree):
    violations = _find_cat_pipe_violations(tree)
    assert not violations, (
        f"Found `cat FILE | hook_lib_pipeline_status_field` in {tree}:\n"
        + "\n".join(violations)
        + "\nUse the redirect form instead: hook_lib_pipeline_status_field <field> < FILE"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. Mutation check: reintroducing the pipe form is caught by test #3.
# ═══════════════════════════════════════════════════════════════════════


def test_mutation_reintroducing_cat_pipe_is_caught(tmp_path):
    mutated_dir = tmp_path / "mutated_hooks"
    mutated_dir.mkdir()
    fixed = (CLAUDE_HOOKS_DIR / "session-boot.sh").read_text()
    assert 'hook_lib_pipeline_status_field phase < "$PIPELINE_STATE_FILE"' in fixed, (
        "Fixture assumption stale: fixed session-boot.sh no longer uses the "
        "redirect form on this exact line -- update this test."
    )
    mutated = fixed.replace(
        'PHASE=$(hook_lib_pipeline_status_field phase < "$PIPELINE_STATE_FILE" 2>/dev/null || echo "idle")',
        'PHASE=$(cat "$PIPELINE_STATE_FILE" | hook_lib_pipeline_status_field phase 2>/dev/null || echo "idle")',
    )
    assert mutated != fixed, "Mutation did not change anything -- pattern text is stale."
    (mutated_dir / "session-boot.sh").write_text(mutated)

    violations = _find_cat_pipe_violations(mutated_dir)
    assert violations, (
        "Structural guard failed to catch a reintroduced cat-pipe mutation "
        "-- the guard is not load-bearing."
    )
