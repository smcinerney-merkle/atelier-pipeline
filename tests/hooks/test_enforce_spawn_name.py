"""Tests for enforce-spawn-name.sh (PreToolUse hook on Agent, G-142).

A generic `claude` agent named `ellis-gd-tag` committed through the
Ellis-only git guard in another repo; a payload named `agatha-disguised`
would skip Colby's path guard and get Agatha's allowlist. Both incidents
share one root cause: every guard identifies an agent by agent_type, and
for a named teammate agent_type is the NAME the spawner chose, not the
definition it was spawned from. This hook refuses a mismatched name at
spawn time, before any downstream guard has to guess.
"""

import json

import pytest

from conftest import HOOKS_DIR, PROJECT_ROOT, prepare_hook, run_hook

HOOK = "enforce-spawn-name.sh"


def build_agent_spawn_input(subagent_type: str | None = None, name: str | None = None) -> str:
    tool_input: dict = {}
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    if name is not None:
        tool_input["name"] = name
    return json.dumps({"tool_name": "Agent", "tool_input": tool_input}, separators=(",", ":"))


def _run(subagent_type=None, name=None, tmp_path=None):
    return run_hook(HOOK, build_agent_spawn_input(subagent_type, name), tmp_path)


def _assert_blocked(r, message_substring=None):
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout
    if message_substring is not None:
        assert message_substring in r.stdout, r.stdout


def _assert_allowed(r):
    assert r.returncode == 0, r.stdout


# ── Refused: naming-rule violations (G-142 incident shapes) ─────────────


REFUSED_CASES = [
    ("claude", "ellis-gd-tag"),        # the Ellis-only git-guard incident
    ("colby", "agatha-disguised"),     # the Colby path-guard incident
    ("colby", "colbyfoo"),             # near-miss: no hyphen boundary
]


@pytest.mark.parametrize("subagent_type,name", REFUSED_CASES)
def test_refused_naming_violation(hook_env, subagent_type, name):
    # Message-specific: rule 3 (OVERLAP) also independently refuses these
    # same cases as a backstop (see hook_lib_agent_base_type's semantics --
    # a name rule 2 refuses can never resolve to subagent_type in rule 3
    # either). Asserting rule 2's own wording keeps this test load-bearing
    # for rule 2 specifically, not just for "refused by something".
    _assert_blocked(_run(subagent_type, name, hook_env), "Hooks identify a named teammate by its name field")


# ── Refused: OVERLAP (name matches a more specific persona) ─────────────


OVERLAP_CASES = [
    ("robert", "robert-spec-x"),
    ("sable", "sable-ux-1"),
]


@pytest.mark.parametrize("subagent_type,name", OVERLAP_CASES)
def test_refused_overlap(hook_env, subagent_type, name):
    _assert_blocked(_run(subagent_type, name, hook_env), "also matches the more specific persona")


def test_refused_investigator_poirot_segment(hook_env):
    """Named Poirot instances must be investigator-<suffix>; poirot-segment
    (Friction's old example) does not start with 'investigator-' and is
    refused by the base naming rule."""
    _assert_blocked(_run("investigator", "poirot-segment", hook_env))


def test_refused_named_with_no_subagent_type(hook_env):
    _assert_blocked(_run(None, "colby-u10", hook_env), "but no subagent_type")


# ── Allowed cases ─────────────────────────────────────────────────────────


ALLOWED_CASES = [
    ("colby", "colby"),
    ("colby", "colby-u10"),
    ("robert-spec", "robert-spec-retro"),
    ("claude", "claude-helper"),
]


@pytest.mark.parametrize("subagent_type,name", ALLOWED_CASES)
def test_allowed_named_spawn(hook_env, subagent_type, name):
    _assert_allowed(_run(subagent_type, name, hook_env))


@pytest.mark.parametrize("subagent_type", ["claude", "colby", "investigator", None])
def test_allowed_unnamed_spawn(hook_env, subagent_type):
    _assert_allowed(_run(subagent_type, None, hook_env))


def test_allowed_non_agent_tool(hook_env):
    hook_path = prepare_hook(HOOK, hook_env)
    import subprocess
    inp = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x", "name": "agatha-disguised"}})
    r = subprocess.run(
        ["bash", str(hook_path)], input=inp, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=30,
    )
    assert r.returncode == 0


# ── Fail-closed when hook-lib.sh is unavailable ──────────────────────────


def test_fails_closed_when_hook_lib_missing(hook_env):
    hook_path = prepare_hook(HOOK, hook_env)
    (hook_path.parent / "hook-lib.sh").unlink()
    import subprocess
    r = subprocess.run(
        ["bash", str(hook_path)],
        input=build_agent_spawn_input("colby", "colby-u10"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(hook_env)},
        timeout=30,
    )
    assert r.returncode == 2
    assert "BLOCKED" in r.stdout


def test_unnamed_spawn_still_allowed_when_hook_lib_missing(hook_env):
    """Fail-closed only applies to NAMED spawns -- an unnamed spawn has
    nothing to verify and must not be penalized by a missing library."""
    hook_path = prepare_hook(HOOK, hook_env)
    (hook_path.parent / "hook-lib.sh").unlink()
    import subprocess
    r = subprocess.run(
        ["bash", str(hook_path)],
        input=build_agent_spawn_input("colby", None),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(hook_env)},
        timeout=30,
    )
    assert r.returncode == 0


# ── Registration: present, no `if`, identical across the 3 copies ────────


REGISTRATION_FILES = [
    PROJECT_ROOT / ".claude" / "settings.json",
]
HOOKS_MD_FILES = [
    PROJECT_ROOT / "skills" / "pipeline-setup" / "hooks.md",
    PROJECT_ROOT / ".cursor-plugin" / "skills" / "pipeline-setup" / "hooks.md",
]


def test_registered_in_settings_json_no_if():
    settings = json.loads((PROJECT_ROOT / ".claude" / "settings.json").read_text())
    agent_matchers = [e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") == "Agent"]
    spawn_hooks = [
        h for m in agent_matchers for h in m.get("hooks", [])
        if "enforce-spawn-name.sh" in h.get("command", "")
    ]
    assert len(spawn_hooks) == 1, spawn_hooks
    assert "if" not in spawn_hooks[0]


@pytest.mark.parametrize("hooks_md", HOOKS_MD_FILES)
def test_registered_in_hooks_md_no_if(hooks_md):
    text = hooks_md.read_text()
    assert 'enforce-spawn-name.sh"}' in text
    assert 'enforce-spawn-name.sh", "if"' not in text


def test_hooks_md_copies_identical_on_spawn_name():
    texts = [f.read_text() for f in HOOKS_MD_FILES]
    assert texts[0] == texts[1]


def test_source_and_installed_hook_identical():
    src = (HOOKS_DIR / HOOK).read_text()
    installed = (PROJECT_ROOT / ".claude" / "hooks" / HOOK).read_text()
    assert src == installed
