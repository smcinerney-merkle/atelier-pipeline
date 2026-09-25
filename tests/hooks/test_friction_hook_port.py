"""Port of Friction's hook fixes (3d760f5, 3dacbdc, 89c7093, 6c45f83, 211d5eb).

Every behavioural test pipes a JSON payload into the real script, installed
the way /pipeline-setup installs it (hook + hook-lib.sh + enforcement-config
in one .claude/hooks/ directory under a temp project root).

Covers:
  - hook_lib_agent_type_matches / hook_lib_agent_base_type (hook-lib.sh)
  - self-gates + per-agent pipeline_state_dir report allowlists in the six
    per-agent path guards, and contract/guard parity with each persona <output>
  - enforce-git.sh anchored write-guard and ellis|ellis-* identity
  - clear-brain-capture-pending.sh main-thread-only guard
  - enforce-brain-capture-pending.sh named-instance match + ADR-0060 roster
  - frontmatter `hooks:` is a record, not a list (Agent type not found)
  - frontmatter command == settings-template command (single run, not double)
  - enforcement-config.json preserve-on-reinstall snippet in hooks.md
  - enforce-colby-stop-verify.sh named-instance match (3d760f5)
  - Colby <output> routes contracts tables to her report, not pipeline-state.md
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import (
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    SHARED_HOOKS_DIR,
    build_bash_input,
    prepare_per_agent_hook,
    run_hook,
)

HOOK_LIB = SHARED_HOOKS_DIR / "hook-lib.sh"
SOURCE_AGENTS = PROJECT_ROOT / "source" / "claude" / "agents"
INSTALLED_AGENTS = PROJECT_ROOT / ".claude" / "agents"
SETUP_HOOKS_MD = [
    PROJECT_ROOT / "skills" / "pipeline-setup" / "hooks.md",
    PROJECT_ROOT / ".cursor-plugin" / "skills" / "pipeline-setup" / "hooks.md",
]

# guard script -> (owning agent, a path the owner may NOT write, tool matcher)
GUARDS = {
    "enforce-colby-paths.sh": ("colby", "docs/architecture/ADR-0001.md", "Write|Edit|MultiEdit"),
    "enforce-sarah-paths.sh": ("sarah", "src/app.py", "Write|Edit"),
    "enforce-ellis-paths.sh": ("ellis", "src/app.py", "Write|Edit|MultiEdit"),
    "enforce-agatha-paths.sh": ("agatha", "src/app.py", "Write|Edit|MultiEdit"),
    "enforce-product-paths.sh": ("robert-spec", "src/app.py", "Write|Edit|MultiEdit"),
    "enforce-ux-paths.sh": ("sable-ux", "src/app.py", "Write|Edit|MultiEdit"),
}
GUARD_AGENT_FILE = {
    "enforce-colby-paths.sh": "colby",
    "enforce-sarah-paths.sh": "sarah",
    "enforce-ellis-paths.sh": "ellis",
    "enforce-agatha-paths.sh": "agatha",
    "enforce-product-paths.sh": "robert-spec",
    "enforce-ux-paths.sh": "sable-ux",
}
# Agents that must pass through each guard untouched (never their guard).
# Includes prefix look-alikes ("colbyalt", "robert", "sable") and Poirot's
# two identities (registered type "investigator", instance names "poirot-*").
BYSTANDERS = {
    "colby": ["sarah", "ellis-reconcile", "colbyalt", "investigator", "poirot-segment"],
    "sarah": ["colby", "colby-u10-tiebreak", "sarahx", "investigator", "poirot-segment"],
    "ellis": ["colby", "sarah-titles", "ellisx", "investigator", "poirot-segment"],
    "agatha": ["colby", "ellis", "agathax", "investigator", "poirot-segment"],
    "robert-spec": ["robert", "robert-review", "colby", "investigator", "poirot-segment"],
    "sable-ux": ["sable", "sable-review", "colby", "investigator", "poirot-segment"],
}


# ── helpers ──────────────────────────────────────────────────────────────


def _clean_env(**extra) -> dict:
    env = os.environ.copy()
    env.pop("ATELIER_SETUP_MODE", None)
    env.pop("CURSOR_PROJECT_DIR", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(extra)
    return env


def _guard_project(tmp_path: Path, state_dir: str = "docs/pipeline") -> Path:
    config = dict(DEFAULT_CONFIG, pipeline_state_dir=state_dir)
    (tmp_path / "enforcement-config.json").write_text(json.dumps(config))
    (tmp_path / state_dir).mkdir(parents=True, exist_ok=True)
    return tmp_path


def run_guard(hook: str, tmp_path: Path, file_path: str, agent_type=None, tool: str = "Write"):
    """Run a path guard with an explicit agent_type (None = key absent)."""
    payload = {"tool_name": tool, "tool_input": {"file_path": file_path}}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    hook_path = prepare_per_agent_hook(hook, tmp_path)
    return subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_clean_env(CLAUDE_PROJECT_DIR=str(tmp_path)),
        timeout=30,
    )


def _lib(fn: str, *args: str) -> subprocess.CompletedProcess:
    quoted = " ".join(f"'{a}'" for a in args)
    return subprocess.run(
        ["bash", "-c", f"source '{HOOK_LIB}'; {fn} {quoted}"],
        capture_output=True, text=True, env=_clean_env(), timeout=10,
    )


def _frontmatter(text: str) -> dict:
    if text.startswith("---\n"):
        text = text[4:text.index("\n---", 4)]
    return yaml.safe_load(text)


def _settings_template(md: Path) -> dict:
    m = re.search(r"```json\n(\{\n  \"env\".*?)\n```", md.read_text(), re.S)
    assert m, f"settings.json template block not found in {md}"
    return json.loads(m.group(1))


# Per-agent report prefixes each guard admits under the state dir (operator
# decision, brain 61f80b99). Direct children only; everything else there is
# Eva's or another agent's and must exit 2.
REPORT_PREFIXES = {
    "colby": ["last-build-*.md", "last-fix-*.md", "last-colby-*.md"],
    "sarah": ["last-adr-*.md"],
    "agatha": ["last-agatha-*.md"],
    "sable-ux": ["last-ux-*.md"],
    "robert-spec": ["last-spec-*.md"],
    "ellis": ["last-commit-*.md", "last-push*.md"],
}
EVA_FILES = ["pipeline-state.md", "context-brief.md", "error-patterns.md",
             "investigation-ledger.md"]
NAMED_INSTANCE = {"colby": "colby-u1", "sarah": "sarah-u1", "agatha": "agatha-u1",
                  "sable-ux": "sable-ux-u1", "robert-spec": "robert-spec-u1",
                  "ellis": "ellis-s27"}
HOOK_FOR = {owner: hook for hook, (owner, _, _) in GUARDS.items()}


def _sample(prefix: str) -> str:
    """A concrete filename for a guard pattern: last-build-*.md -> last-build-x.md."""
    return prefix.replace("*", "x")


def _allowed_samples(owner: str) -> list[str]:
    names = [_sample(p) for p in REPORT_PREFIXES[owner]]
    if owner == "ellis":
        names += ["last-push.md", "last-push-w2.md"]  # both forms Friction uses
    return names


# ── hook-lib.sh matcher ──────────────────────────────────────────────────


@pytest.mark.parametrize("agent,bases,expected", [
    ("colby", ["colby"], 0),
    ("colby-u10-tiebreak", ["colby"], 0),
    ("colbyalt", ["colby"], 1),
    ("", ["colby"], 1),
    ("poirot-segment", ["investigator", "poirot"], 0),
    ("investigator", ["investigator", "poirot"], 0),
    ("poirot-segment", ["investigator"], 1),
])
def test_agent_type_matches(agent, bases, expected):
    assert _lib("hook_lib_agent_type_matches", agent, *bases).returncode == expected


@pytest.mark.parametrize("agent,expected", [
    ("robert", "robert"),
    ("robert-review", "robert"),
    ("robert-spec", "robert-spec"),
    ("robert-spec-retro", "robert-spec"),
    ("sable-ux-overlay", "sable-ux"),
    ("sable-history", "sable"),
])
def test_agent_base_type_prefers_longest(agent, expected):
    r = _lib("hook_lib_agent_base_type", agent, "robert", "robert-spec", "sable", "sable-ux")
    assert r.returncode == 0 and r.stdout.strip() == expected


def test_agent_base_type_no_match():
    r = _lib("hook_lib_agent_base_type", "colbyalt", "colby")
    assert r.returncode == 1 and r.stdout == ""


# ── six per-agent path guards ────────────────────────────────────────────


@pytest.mark.parametrize("hook", list(GUARDS))
@pytest.mark.parametrize("instance", ["bare", "named"])
def test_guard_blocks_owner_on_forbidden_path(tmp_path, hook, instance):
    owner, forbidden, _ = GUARDS[hook]
    agent = owner if instance == "bare" else f"{owner}-u7-probe"
    r = run_guard(hook, _guard_project(tmp_path), forbidden, agent)
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("hook", list(GUARDS))
@pytest.mark.parametrize("instance", ["bare", "named"])
@pytest.mark.parametrize("state_dir", ["docs/pipeline", "pipeline-state"])
def test_guard_allows_owner_in_state_dir(tmp_path, hook, instance, state_dir):
    # "pipeline-state" sits outside every agent's own allowlist (including
    # Agatha's docs/*), so only the configured exemption can allow it.
    owner, _, _ = GUARDS[hook]
    agent = owner if instance == "bare" else f"{owner}-u7-probe"
    report = _sample(REPORT_PREFIXES[owner][0])
    r = run_guard(hook, _guard_project(tmp_path, state_dir), f"{state_dir}/{report}", agent)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("hook", list(GUARDS))
def test_guard_state_dir_exemption_is_config_driven(tmp_path, hook):
    # With the state dir moved, the default docs/pipeline/ is no longer exempt
    # for agents whose allowlist does not cover it.
    owner, _, _ = GUARDS[hook]
    if owner in ("colby", "agatha"):
        pytest.skip("docs/pipeline is covered by this agent's own rules")
    r = run_guard(hook, _guard_project(tmp_path, "pipeline-state"), "docs/pipeline/x.md", owner)
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("hook", list(GUARDS))
def test_guard_state_dir_traversal_still_blocked(tmp_path, hook):
    owner, _, _ = GUARDS[hook]
    r = run_guard(hook, _guard_project(tmp_path), "docs/pipeline/../../src/app.py", owner)
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("hook", list(GUARDS))
def test_guard_passes_bystanders(tmp_path, hook):
    owner, forbidden, _ = GUARDS[hook]
    project = _guard_project(tmp_path)
    for agent in BYSTANDERS[owner]:
        r = run_guard(hook, project, forbidden, agent)
        assert r.returncode == 0, f"{hook} blocked bystander {agent!r}: {r.stdout}"


@pytest.mark.parametrize("hook", list(GUARDS))
@pytest.mark.parametrize("agent_type", [None, ""])
def test_guard_passes_main_thread(tmp_path, hook, agent_type):
    _, forbidden, _ = GUARDS[hook]
    r = run_guard(hook, _guard_project(tmp_path), forbidden, agent_type)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("hook", list(GUARDS))
def test_guard_loud_fallback_without_hook_lib(tmp_path, hook):
    owner, forbidden, _ = GUARDS[hook]
    project = _guard_project(tmp_path)
    hook_path = prepare_per_agent_hook(hook, project)
    (hook_path.parent / "hook-lib.sh").unlink()
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": forbidden},
                          "agent_type": owner})
    r = subprocess.run(["bash", str(hook_path)], input=payload, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True,
                       env=_clean_env(CLAUDE_PROJECT_DIR=str(project)), timeout=30)
    assert r.returncode == 2
    assert "WARNING" in r.stdout and "hook-lib.sh unavailable" in r.stdout


# ── enforce-git.sh ───────────────────────────────────────────────────────

DESTRUCTIVE_CHECKOUTS = [
    "git checkout -- .",
    "git checkout -- *",
    "git checkout -- src/x.ts",
    "git checkout HEAD -- .",
    "git checkout .",
    "git checkout -f",
    "git checkout -fq",
    "git checkout -qf",
    # regressions: already blocked before the port, must stay blocked
    "git checkout --force main",
    "git checkout --ours src/x.ts",
    "git checkout --theirs src/x.ts",
    "git checkout --patch",
]

# G-147 FLIP: a bare "git checkout --detach" (and "--track"/"--help") moved
# out of DESTRUCTIVE_CHECKOUTS above. G-147 ports Guru's GIT_WRITE_EXEMPT
# allowlist into this fork's enforce-git.sh, which explicitly exempts a bare
# long-form checkout with no trailing arg (or a trailing arg not starting
# with '-' or '.') as a non-destructive branch operation. See
# tests/hooks/test_enforce_git_rf_parity.py's matching G-147 FLIP comment.
GIT_CHECKOUT_EXEMPT_LONGFORMS = [
    "git checkout --detach",
    "git checkout --track",
    "git checkout --help",
]


def _git(tmp_path, command, agent_type=None, agent_id=None):
    return run_hook("enforce-git.sh", build_bash_input(command, agent_id=agent_id,
                    agent_type=agent_type), tmp_path)


@pytest.mark.parametrize("command", DESTRUCTIVE_CHECKOUTS)
def test_git_destructive_checkout_blocked_main_thread(tmp_path, command):
    r = _git(tmp_path, command)
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("command", DESTRUCTIVE_CHECKOUTS + ["git commit -m x", "git push"])
def test_git_write_blocked_for_non_ellis_named_instance(tmp_path, command):
    r = _git(tmp_path, command, agent_type="colby-u10-tiebreak", agent_id="a1")
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("agent", ["ellis", "ellis-reconcile"])
@pytest.mark.parametrize("command", ["git commit -m x", "git push origin main", "git checkout -- ."])
def test_git_write_allowed_for_ellis(tmp_path, agent, command):
    r = _git(tmp_path, command, agent_type=agent, agent_id="a1")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("agent", ["ellisx", "not-ellis"])
def test_git_ellis_lookalike_blocked(tmp_path, agent):
    r = _git(tmp_path, "git commit -m x", agent_type=agent, agent_id="a1")
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("command", GIT_CHECKOUT_EXEMPT_LONGFORMS)
def test_git_checkout_exempt_longforms_allowed_for_non_ellis(tmp_path, command):
    """G-147: bare checkout --detach/--track/--help are exempt (non-destructive
    branch operations), allowed for every agent, not just Ellis."""
    r = _git(tmp_path, command, agent_type="colby-u10-tiebreak", agent_id="a1")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", [
    "git checkout main",
    "git checkout -b feature/x",
    "git status && git diff",
    "echo 'remember to git add later'",
    "grep -rn 'git commit' docs/",
])
def test_git_nondestructive_or_unanchored_allowed(tmp_path, command):
    r = _git(tmp_path, command)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", [
    "cd repo && git add .",
    "true; git commit -m x",
    "(git reset --hard)",
    "ls | git clean -fd",
])
def test_git_anchored_positions_blocked(tmp_path, command):
    r = _git(tmp_path, command)
    assert r.returncode == 2, r.stdout


# ── clear-brain-capture-pending.sh ───────────────────────────────────────


def _brain_project(tmp_path: Path) -> Path:
    (tmp_path / "enforcement-config.json").write_text(json.dumps(DEFAULT_CONFIG))
    (tmp_path / "docs" / "pipeline").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _marker(tmp_path: Path) -> Path:
    return tmp_path / "docs" / "pipeline" / ".pending-brain-capture.json"


def _clear(tmp_path, payload):
    return run_hook("clear-brain-capture-pending.sh", json.dumps(payload), tmp_path,
                    env_override={"CLAUDE_PROJECT_DIR": str(tmp_path)})


def test_clear_pending_subagent_capture_keeps_marker(tmp_path):
    project = _brain_project(tmp_path)
    _marker(project).write_text('{"agent_type":"colby"}')
    r = _clear(project, {"tool_name": "mcp__mybrain__agent_capture",
                         "agent_id": "sub-123", "agent_type": "colby"})
    assert r.returncode == 0
    assert _marker(project).exists(), "a subagent's capture cleared Eva's marker"


def test_clear_pending_main_thread_capture_clears_marker(tmp_path):
    project = _brain_project(tmp_path)
    _marker(project).write_text('{"agent_type":"colby"}')
    r = _clear(project, {"tool_name": "mcp__mybrain__agent_capture"})
    assert r.returncode == 0
    assert not _marker(project).exists()


def test_clear_pending_other_tool_keeps_marker(tmp_path):
    project = _brain_project(tmp_path)
    _marker(project).write_text('{"agent_type":"colby"}')
    _clear(project, {"tool_name": "mcp__mybrain__agent_search"})
    assert _marker(project).exists()


# ── enforce-brain-capture-pending.sh ─────────────────────────────────────


def _stop(tmp_path, agent_type, roster=None):
    if roster is not None:
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "pipeline-config.json").write_text(
            json.dumps({"agent_roster": roster}))
    payload = {"agent_type": agent_type, "agent_id": "a1", "session_id": "s1"}
    return run_hook("enforce-brain-capture-pending.sh", json.dumps(payload), tmp_path,
                    env_override={"CLAUDE_PROJECT_DIR": str(tmp_path)})


@pytest.mark.parametrize("agent", ["colby-u10-tiebreak", "sarah-titles", "ellis-reconcile",
                                   "robert-spec-retro", "sable-ux-overlay", "colby"])
def test_pending_named_instance_writes_marker(tmp_path, agent):
    project = _brain_project(tmp_path)
    r = _stop(project, agent)
    assert r.returncode == 0
    assert _marker(project).exists(), f"{agent} did not write the marker"
    assert json.loads(_marker(project).read_text())["agent_type"] == agent


@pytest.mark.parametrize("agent", ["investigator", "poirot-segment", "colbyalt", "scout", ""])
def test_pending_non_allowlisted_no_marker(tmp_path, agent):
    project = _brain_project(tmp_path)
    _stop(project, agent)
    assert not _marker(project).exists()


@pytest.mark.parametrize("agent", ["colby", "colby-u10-tiebreak"])
@pytest.mark.parametrize("roster,expected", [
    ({"colby": {"enabled": True}}, True),
    ({"colby": {"enabled": False}}, False),
    ({"sarah": {"enabled": True}}, False),  # present roster, colby absent = disabled
])
def test_pending_roster_applies_to_base_type(tmp_path, agent, roster, expected):
    project = _brain_project(tmp_path)
    _stop(project, agent, roster)
    assert _marker(project).exists() is expected


@pytest.mark.parametrize("agent,expected", [
    ("robert-spec-retro", True),   # roster-exempt producer, resolved by longest base
    ("robert-review", False),      # reviewer robert, absent from roster
    ("sable-ux-overlay", True),
    ("sable-history", True),       # sable (reviewer) is always-on
])
def test_pending_roster_exemptions_survive_prefix_match(tmp_path, agent, expected):
    project = _brain_project(tmp_path)
    _stop(project, agent, {"colby": {"enabled": True}})
    assert _marker(project).exists() is expected


# ── frontmatter shape + settings parity (findings 1 and 2) ───────────────


def _hooked_frontmatters():
    out = []
    for p in sorted(SOURCE_AGENTS.glob("*.frontmatter.yml")):
        out.append(p)
    for p in sorted(INSTALLED_AGENTS.glob("*.md")):
        out.append(p)
    return out


@pytest.mark.parametrize("path", _hooked_frontmatters(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_frontmatter_hooks_is_record(path):
    fm = _frontmatter(path.read_text())
    if "hooks" not in fm:
        pytest.skip("no hooks")
    hooks = fm["hooks"]
    assert isinstance(hooks, dict), (
        f"{path}: hooks: is a {type(hooks).__name__}; the list form fails schema "
        "validation (expected \"record\") and drops the whole agent definition")
    for event, groups in hooks.items():
        assert isinstance(groups, list), f"{path}: hooks.{event} must be a list"
        for g in groups:
            assert isinstance(g, dict) and isinstance(g.get("hooks"), list), path
            for h in g["hooks"]:
                assert h.get("type") == "command" and h.get("command"), path


def test_all_six_guards_declared_in_frontmatter():
    for hook, agent in GUARD_AGENT_FILE.items():
        fm = _frontmatter((SOURCE_AGENTS / f"{agent}.frontmatter.yml").read_text())
        cmds = [h["command"] for g in fm["hooks"]["PreToolUse"] for h in g["hooks"]]
        assert any(c.endswith(f"/.claude/hooks/{hook}") for c in cmds), agent


def _template_commands(md: Path) -> dict:
    """Map guard script -> (command, matcher) from the settings template."""
    out = {}
    for group in _settings_template(md)["hooks"]["PreToolUse"]:
        for h in group["hooks"]:
            cmd = h.get("command", "")
            for hook in GUARDS:
                if cmd.endswith("/" + hook):
                    out[hook] = (cmd, group["matcher"])
    return out


@pytest.mark.parametrize("md", SETUP_HOOKS_MD, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
@pytest.mark.parametrize("hook", list(GUARDS))
def test_frontmatter_command_equals_settings_template(md, hook):
    template = _template_commands(md)
    assert hook in template, f"{hook} not registered in {md}"
    t_cmd, t_matcher = template[hook]
    agent = GUARD_AGENT_FILE[hook]
    for src in (SOURCE_AGENTS / f"{agent}.frontmatter.yml", INSTALLED_AGENTS / f"{agent}.md"):
        group = _frontmatter(src.read_text())["hooks"]["PreToolUse"][0]
        fm_cmd = group["hooks"][0]["command"]
        assert fm_cmd == t_cmd, (
            f"{src.name} command {fm_cmd!r} != settings template {t_cmd!r}; "
            "any difference makes Claude Code run the guard twice")
        assert group["matcher"] == t_matcher == GUARDS[hook][2], src


# ── enforcement-config.json preserve snippet (hooks.md) ──────────────────


def _preserve_snippet() -> str:
    text = SETUP_HOOKS_MD[0].read_text()
    m = re.search(r"#### Preserve an existing enforcement-config\.json.*?```bash\n(.*?)```", text, re.S)
    assert m, "preserve snippet missing from hooks.md"
    return m.group(1)


def _run_preserve(tmp_path: Path) -> subprocess.CompletedProcess:
    plugin = tmp_path / "plugin"
    (plugin / "source" / "claude" / "hooks").mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "source" / "claude" / "hooks" / "enforcement-config.json",
                 plugin / "source" / "claude" / "hooks" / "enforcement-config.json")
    (tmp_path / "proj" / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    return subprocess.run(["bash", "-c", _preserve_snippet() + '\necho "ADDED=[$ADDED]"'],
                          cwd=tmp_path / "proj", capture_output=True, text=True,
                          env=_clean_env(CLAUDE_PLUGIN_ROOT=str(plugin)), timeout=30)


def test_preserve_existing_config_adds_only_missing_keys(tmp_path):
    installed = tmp_path / "proj" / ".claude" / "hooks" / "enforcement-config.json"
    installed.parent.mkdir(parents=True)
    installed.write_text(json.dumps({"pipeline_state_dir": "state/x", "test_command": "",
                                     "custom_key": 7}))
    r = _run_preserve(tmp_path)
    assert r.returncode == 0, r.stderr
    got = json.loads(installed.read_text())
    assert got["pipeline_state_dir"] == "state/x"
    assert got["test_command"] == ""          # present-but-empty is not rewritten
    assert got["custom_key"] == 7
    assert got["test_patterns"] and got["colby_blocked_paths"]
    assert "ADDED=[colby_blocked_paths\ntest_patterns]" in r.stdout


def test_preserve_complete_config_unchanged(tmp_path):
    installed = tmp_path / "proj" / ".claude" / "hooks" / "enforcement-config.json"
    installed.parent.mkdir(parents=True)
    original = json.dumps({"pipeline_state_dir": "p", "test_command": "make t",
                           "test_patterns": ["x"], "colby_blocked_paths": ["y/"]})
    installed.write_text(original)
    r = _run_preserve(tmp_path)
    assert r.returncode == 0 and "ADDED=[]" in r.stdout
    assert installed.read_text() == original  # byte-identical: not even rewritten


def test_preserve_absent_config_copies_template(tmp_path):
    r = _run_preserve(tmp_path)
    assert r.returncode == 0
    installed = tmp_path / "proj" / ".claude" / "hooks" / "enforcement-config.json"
    assert json.loads(installed.read_text()) == json.loads(
        (PROJECT_ROOT / "source" / "claude" / "hooks" / "enforcement-config.json").read_text())


# ── triple-target sync ───────────────────────────────────────────────────

SYNCED = [
    ("source/shared/hooks/hook-lib.sh", ".claude/hooks/hook-lib.sh"),
    ("source/shared/hooks/hook-lib.sh", ".cursor-plugin/hooks/hook-lib.sh"),
    ("skills/pipeline-setup/hooks.md", ".cursor-plugin/skills/pipeline-setup/hooks.md"),
] + [(f"source/claude/hooks/{h}", f".claude/hooks/{h}") for h in [
    *GUARDS, "enforce-git.sh", "clear-brain-capture-pending.sh",
    "enforce-brain-capture-pending.sh", "enforce-colby-stop-verify.sh"]]


@pytest.mark.parametrize("src,dst", SYNCED, ids=[d for _, d in SYNCED])
def test_installed_copy_matches_source(src, dst):
    assert (PROJECT_ROOT / src).read_bytes() == (PROJECT_ROOT / dst).read_bytes()


# ── enforce-colby-stop-verify.sh ─────────────────────────────────────────


def _stop_verify(tmp_path: Path, agent_type, with_lib: bool = True):
    """Run the stop-verify hook with a typecheck stub that leaves a sentinel
    and fails. Sentinel present + exit 2 = the verify logic was reached."""
    sentinel = tmp_path / "typecheck-was-invoked"
    stub = tmp_path / "fake-typecheck"
    stub.write_text(f"#!/bin/bash\ntouch '{sentinel}'\necho 'error: boom' >&2\nexit 1\n")
    stub.chmod(0o755)
    (tmp_path / "docs" / "pipeline").mkdir(parents=True, exist_ok=True)
    hook_path = prepare_per_agent_hook("enforce-colby-stop-verify.sh", tmp_path)
    if not with_lib:
        (hook_path.parent / "hook-lib.sh").unlink()
    (tmp_path / ".claude" / "pipeline-config.json").write_text(
        json.dumps({"verify_commands": {"typecheck": str(stub)}}))
    payload = {"agent_id": "a1", "session_id": "s-stopverify"}
    if agent_type is not None:
        payload["agent_type"] = agent_type
    r = subprocess.run(["bash", str(hook_path)], input=json.dumps(payload),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=_clean_env(CLAUDE_PROJECT_DIR=str(tmp_path)), timeout=30)
    return r, sentinel.exists()


@pytest.mark.parametrize("agent", ["colby", "colby-u10-tiebreak"])
def test_stop_verify_reaches_verify_logic(tmp_path, agent):
    r, ran = _stop_verify(tmp_path, agent)
    assert ran, f"{agent}: typecheck never ran -- the agent gate exited early"
    assert r.returncode == 2, r.stdout


@pytest.mark.parametrize("agent", ["colbyx", "sarah", "ellis-reconcile", "investigator",
                                   "poirot-segment", "", None])
def test_stop_verify_exits_early_for_others(tmp_path, agent):
    r, ran = _stop_verify(tmp_path, agent)
    assert r.returncode == 0 and not ran, f"{agent!r} reached the verify logic"


def test_stop_verify_loud_fallback_without_hook_lib(tmp_path):
    r, ran = _stop_verify(tmp_path, "colby-u10-tiebreak", with_lib=False)
    assert "WARNING" in r.stdout and "hook-lib.sh unavailable" in r.stdout
    assert r.returncode == 0 and not ran   # fail-narrow: named instance skipped
    r, ran = _stop_verify(tmp_path, "colby", with_lib=False)
    assert ran and r.returncode == 2       # bare colby still verified


# ── state-dir report allowlist (per agent) ───────────────────────────────

OWNER_INSTANCES = [(o, i) for o in REPORT_PREFIXES for i in ("bare", "named")]


def _agent(owner: str, instance: str) -> str:
    return owner if instance == "bare" else NAMED_INSTANCE[owner]


@pytest.mark.parametrize("owner,instance", OWNER_INSTANCES)
@pytest.mark.parametrize("eva_file", EVA_FILES)
def test_state_dir_blocks_eva_files(tmp_path, owner, instance, eva_file):
    r = run_guard(HOOK_FOR[owner], _guard_project(tmp_path), f"docs/pipeline/{eva_file}",
                  _agent(owner, instance))
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("owner,instance", OWNER_INSTANCES)
def test_state_dir_allows_own_reports(tmp_path, owner, instance):
    project = _guard_project(tmp_path)
    for name in _allowed_samples(owner):
        r = run_guard(HOOK_FOR[owner], project, f"docs/pipeline/{name}", _agent(owner, instance))
        assert r.returncode == 0, f"{owner} blocked on own report {name}: {r.stdout}"


@pytest.mark.parametrize("owner,instance", OWNER_INSTANCES)
def test_state_dir_blocks_sibling_and_other_reports(tmp_path, owner, instance):
    project = _guard_project(tmp_path)
    others = [n for o in REPORT_PREFIXES if o != owner for n in _allowed_samples(o)]
    for name in others + ["last-qa-report.md", "last-case-file.md"]:
        r = run_guard(HOOK_FOR[owner], project, f"docs/pipeline/{name}", _agent(owner, instance))
        assert r.returncode == 2, f"{owner} allowed foreign file {name}: {r.stdout}"


@pytest.mark.parametrize("owner,instance", OWNER_INSTANCES)
def test_state_dir_blocks_slash_after_prefix(tmp_path, owner, instance):
    # bash case "*" matches "/", so last-build-*.md alone would admit these.
    project = _guard_project(tmp_path)
    for prefix in REPORT_PREFIXES[owner]:
        nested = prefix.replace("*.md", "x/pipeline-state.md")
        r = run_guard(HOOK_FOR[owner], project, f"docs/pipeline/{nested}", _agent(owner, instance))
        assert r.returncode == 2, f"{owner} allowed nested path {nested}: {r.stdout}"


@pytest.mark.parametrize("instance", ["bare", "named"])
@pytest.mark.parametrize("path", ["docs/guide/setup.md", "docs/architecture/README.md",
                                  "docs/pipeline-notes.md", "docs/index.md"])
def test_agatha_docs_writes_outside_state_dir_allowed(tmp_path, instance, path):
    r = run_guard("enforce-agatha-paths.sh", _guard_project(tmp_path), path,
                  _agent("agatha", instance))
    assert r.returncode == 0, r.stdout


def _guard_report_patterns(hook: str) -> set[str]:
    text = (PROJECT_ROOT / "source" / "claude" / "hooks" / hook).read_text()
    arms = re.findall(r"^\s+(last-[^)\s]*)\) exit 0 ;;$", text, re.M)
    assert len(arms) == 1, f"{hook}: expected one report-allowlist arm, found {arms}"
    return set(arms[0].split("|"))


def _contract_report_patterns(md: Path) -> set[str]:
    lines = md.read_text().split("\n")
    start = lines.index("<output>")
    block = "\n".join(lines[start:lines.index("</output>", start)])
    found = re.findall(r"\{pipeline_state_dir\}/(last-[a-z-]*?)(?:<slug>|<suffix>)\.md", block)
    return {f"{p}*.md" for p in found}


@pytest.mark.parametrize("owner", list(REPORT_PREFIXES))
@pytest.mark.parametrize("tree", ["source/shared/agents", ".claude/agents"])
def test_contract_matches_guard(owner, tree):
    hook = HOOK_FOR[owner]
    guard = _guard_report_patterns(hook)
    contract = _contract_report_patterns(PROJECT_ROOT / tree / f"{owner}.md")
    assert guard == set(REPORT_PREFIXES[owner]), f"{hook} allows {guard}"
    assert contract == guard, f"{tree}/{owner}.md names {contract}, guard allows {guard}"


COLBY_COPIES = [
    "source/shared/agents/colby.md",
    ".claude/agents/colby.md",
    ".cursor-plugin/agents/colby.md",
]


@pytest.mark.parametrize("rel", COLBY_COPIES)
def test_colby_output_keeps_tables_out_of_pipeline_state(rel):
    lines = (PROJECT_ROOT / rel).read_text().split("\n")
    start = lines.index("<output>")
    block = "\n".join(lines[start:lines.index("</output>", start)])
    assert "pipeline-state.md" not in block, f"{rel} <output> directs a write to pipeline-state.md"
    assert not re.search(r"contracts tables go in\s+`[^`]*pipeline-state", block, re.I), rel
    assert re.search(r"contracts tables go in your\s+report:\s+`[^`]*/last-build-<slug>\.md`", block), (
        f"{rel} <output> does not route tables to last-build-<slug>.md"
    )
