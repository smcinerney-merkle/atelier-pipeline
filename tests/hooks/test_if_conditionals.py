"""Tests for ADR-0020 Step 1: `if` conditionals on existing hooks. Covers T-0020-001 through T-0020-010."""

import json
import subprocess

from conftest import (
    PROJECT_ROOT,
    build_agent_input,
    build_bash_input,
    build_tool_input,
    run_hook,
    write_pipeline_status,
)


def test_T_0020_001_enforce_git_has_no_if_field():
    """G-107/G-143 supersedes: the `if` conditional this test used to require
    (`tool_input.command.includes('git ')`) never fired. A probe on CLI
    2.1.282 (Eva, this session) confirmed the harness's `if` evaluates a
    narrow permission-rule form, not arbitrary JS: `Bash(git *)` fires,
    but a JS-expression `if` like this one never does, for Bash or Agent.
    That meant enforce-git.sh's installed registration never ran the
    script at all -- an install-wide silent no-op, not a performance
    optimization. The `if` has been removed from every registration copy
    (.claude/settings.json, skills/pipeline-setup/hooks.md,
    .cursor-plugin/skills/pipeline-setup/hooks.md); the script now runs on
    every Bash call and relies on its own internal TOOL_NAME/COMMAND
    checks to stay cheap. This test now asserts the `if` field is ABSENT,
    the inverse of what it asserted before."""
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text())
    bash_matchers = [e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
    git_hooks = [
        h for m in bash_matchers for h in m.get("hooks", [])
        if "enforce-git.sh" in h.get("command", "")
    ]
    assert len(git_hooks) >= 1
    assert "if" not in git_hooks[0], (
        f"enforce-git.sh registration must have no `if` field (G-107/G-143 -- "
        f"the harness's `if` evaluator never matched it, so the script never "
        f"ran). Found: {git_hooks[0]!r}"
    )


# ADR-0025 supersedes: warn-dor-dod.sh deleted from SubagentStop; replaced by session-hydrate.sh in SessionStart (ADR-0025 R11, R9)
# Hook wiring audit: session-hydrate.sh is now a no-op and was removed from SessionStart.
# session-hydrate-enforcement.sh replaces it for actual enforcement hydration.
def test_T_0020_002_warn_dor_dod_if_field():
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text())
    stop_matchers = settings["hooks"].get("SubagentStop", [])
    # warn-dor-dod.sh must be absent from SubagentStop after ADR-0025
    dod_hooks = [
        h for m in stop_matchers for h in m.get("hooks", [])
        if h.get("command") and "warn-dor-dod.sh" in h["command"]
    ]
    assert len(dod_hooks) == 0, (
        "warn-dor-dod.sh must not appear in SubagentStop after ADR-0025 deleted it. "
        f"Found: {dod_hooks}"
    )
    # session-hydrate.sh is now a no-op intentionally removed from SessionStart.
    # The real enforcement hydration is handled by session-hydrate-enforcement.sh.
    session_start = settings["hooks"].get("SessionStart", [])
    hydrate_noop_hooks = [
        h for m in session_start for h in m.get("hooks", [])
        if h.get("command") and "session-hydrate.sh" in h["command"]
        and "enforcement" not in h["command"]
    ]
    assert len(hydrate_noop_hooks) == 0, (
        "session-hydrate.sh (no-op) must NOT be registered in SessionStart. "
        f"Found: {hydrate_noop_hooks}"
    )


def test_T_0020_003_regression_enforce_git(hook_env):
    r = run_hook("enforce-git.sh", build_bash_input("git commit -m test"), hook_env)
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_T_0020_004_regression_enforce_paths(hook_env):
    r = run_hook("enforce-eva-paths.sh", build_tool_input("Write", "docs/guide/foo.md", ""), hook_env)
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_T_0020_005_regression_enforce_sequencing(hook_env):
    write_pipeline_status(hook_env, '{"roz_qa":"FAIL","phase":"review"}')
    (hook_env / "enforcement-config.json").write_text(
        json.dumps({"pipeline_state_dir": str(hook_env / "docs" / "pipeline")})
    )
    r = run_hook("enforce-sequencing.sh", build_agent_input("ellis"), hook_env)
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_T_0020_006_regression_enforce_pipeline_activation(hook_env):
    (hook_env / "docs" / "pipeline" / "pipeline-state.md").unlink(missing_ok=True)
    (hook_env / "enforcement-config.json").write_text(
        json.dumps({"pipeline_state_dir": str(hook_env / "docs" / "pipeline")})
    )
    r = run_hook("enforce-pipeline-activation.sh", build_agent_input("colby"), hook_env)
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_T_0020_007_skill_md_and_settings_agree_no_if_for_enforce_git():
    """G-107/G-143 supersedes: this test used to assert the two copies of
    enforce-git.sh's `if` value matched each other. The `if` never fired on
    either copy (see test_T_0020_001's docstring) and has been removed from
    both. This test now asserts parity on absence instead of parity on a
    dead value."""
    settings_file = PROJECT_ROOT / ".claude" / "settings.json"
    # Hook manifest (including JSON template with if conditions) moved to hooks.md per ADR-0058.
    hooks_file = PROJECT_ROOT / "skills" / "pipeline-setup" / "hooks.md"
    assert settings_file.exists()
    assert hooks_file.exists()

    settings = json.loads(settings_file.read_text())
    hooks_text = hooks_file.read_text()

    bash_matchers = [e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
    git_hooks = [
        h for m in bash_matchers for h in m.get("hooks", [])
        if "enforce-git.sh" in h.get("command", "")
    ]
    assert "if" not in git_hooks[0]
    assert '"enforce-git.sh", "if"' not in hooks_text
    assert "enforce-git.sh\"}]" in hooks_text or '"enforce-git.sh"}]' in hooks_text

    # warn-dor-dod.sh removed in ADR-0025; session-hydrate.sh (SessionStart) has no if condition


def test_T_0020_008_enforce_git_direct_call(hook_env):
    r = run_hook("enforce-git.sh", build_bash_input("git commit -m 'test message'"), hook_env)
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_T_0020_009_enforce_git_has_no_if_field_at_all():
    """G-107/G-143 supersedes: see test_T_0020_001's docstring. `if_val` must
    now be None (key absent), not a non-empty string."""
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text())
    bash_matchers = [e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
    git_hooks = [
        h for m in bash_matchers for h in m.get("hooks", [])
        if "enforce-git.sh" in h.get("command", "")
    ]
    if_val = git_hooks[0].get("if")
    assert if_val is None


# ADR-0025 supersedes: warn-dor-dod.sh deleted from SubagentStop; SessionStart carries session-hydrate.sh instead (ADR-0025 R11, R9)
# Hook wiring audit: session-hydrate.sh is now a no-op and removed from SessionStart.
# ADR-0055 Phase 3 (brain extraction): session-hydrate-enforcement.sh removed -- it depended on
# brain/scripts/hydrate-enforcement.mjs which no longer exists in the pipeline repo.
def test_T_0020_010_warn_dor_dod_if_field_type():
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text())
    stop_matchers = settings["hooks"].get("SubagentStop", [])
    # warn-dor-dod.sh must not be present in SubagentStop after ADR-0025
    dod_hooks = [
        h for m in stop_matchers for h in m.get("hooks", [])
        if h.get("command") and "warn-dor-dod.sh" in h["command"]
    ]
    assert len(dod_hooks) == 0, (
        "warn-dor-dod.sh must not appear in SubagentStop after ADR-0025 deleted it."
    )
    # session-hydrate-enforcement.sh must NOT be registered after brain extraction (ADR-0055 Phase 3).
    # The hook depended on brain/scripts/hydrate-enforcement.mjs which is no longer in this repo.
    session_start = settings["hooks"].get("SessionStart", [])
    enforcement_hooks = [
        h for m in session_start for h in m.get("hooks", [])
        if h.get("command") and "session-hydrate-enforcement.sh" in h["command"]
    ]
    assert len(enforcement_hooks) == 0, (
        "session-hydrate-enforcement.sh must not be registered after brain extraction (ADR-0055 Phase 3)."
    )
