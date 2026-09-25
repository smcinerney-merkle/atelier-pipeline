"""Replay of strategy_workbench_portal's enforce-git.sh regression corpus
against this fork's enforce-git.sh (G-151 item 2, operator decision P6).

Ported from apps/shell/tests/enforce-git-hook.cases.ts -- see
tests/hooks/data/portal_enforce_git_corpus.json's own "provenance" block for
the exact source commit and what was deliberately NOT ported (the portal's
two pattern-provenance tests and four derived-count tests stay local to the
portal; its own regex strings are not re-asserted here, only its behavior).

140 cases, five kinds:
  - guard: the core git-write / checkout / switch / stash / merge / gc /
    prune / reflog / filter-branch behavior, across identities (main
    thread, colby, ellis, poirot, etc.).
  - setup_mode_file: the docs/pipeline/.setup-mode kill-switch sentinel.
  - atelier_setup_mode_env: the ATELIER_SETUP_MODE=1/0 env-var kill switch.
  - tool_name: the tool_name != Bash short-circuit.
  - git_available: the pipeline-config.json git_available:false switch.

Every row replays at the EXACT expect_exit the portal's own corpus recorded
-- including the kill-switch variants and the portal's `ee-01` row (kept as
data, unaltered, per operator instruction)."""

import json
from pathlib import Path

import pytest

from conftest import build_bash_input, run_hook, run_hook_with_project_dir

HOOK = "enforce-git.sh"
DATA_PATH = Path(__file__).parent / "data" / "portal_enforce_git_corpus.json"
_DATA = json.loads(DATA_PATH.read_text())
CASES = _DATA["cases"]

_BY_KIND = {}
for _c in CASES:
    _BY_KIND.setdefault(_c["kind"], []).append(_c)

GUARD_CASES = _BY_KIND["guard"]
SETUP_MODE_FILE_CASES = _BY_KIND["setup_mode_file"]
ATELIER_SETUP_MODE_ENV_CASES = _BY_KIND["atelier_setup_mode_env"]
TOOL_NAME_CASES = _BY_KIND["tool_name"]
GIT_AVAILABLE_CASES = _BY_KIND["git_available"]


def test_corpus_has_140_cases():
    """Pin the corpus size -- if this drops, a category was dropped on
    ingest; if it grows, the provenance block's total_cases needs updating
    alongside it."""
    assert len(CASES) == 140
    assert _DATA["provenance"]["total_cases"] == 140


@pytest.mark.parametrize("case", GUARD_CASES, ids=[c["id"] for c in GUARD_CASES])
def test_portal_guard_case(hook_env, case):
    agent_type = case["agent_type"] or None
    r = run_hook(HOOK, build_bash_input(case["command"], agent_type=agent_type), hook_env)
    assert r.returncode == case["expect_exit"], (
        f"{case['id']} ({case['note']}): command={case['command']!r} "
        f"agent_type={case['agent_type']!r} expected {case['expect_exit']}, got "
        f"{r.returncode}. stdout={r.stdout!r}"
    )


@pytest.mark.parametrize("case", SETUP_MODE_FILE_CASES, ids=[c["id"] for c in SETUP_MODE_FILE_CASES])
def test_portal_setup_mode_file_case(hook_env, case):
    # The sentinel check reads ${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}},
    # so CLAUDE_PROJECT_DIR must point at hook_env for the sentinel file to
    # be found at all -- plain run_hook() strips both project-dir vars.
    if case["setup_mode_file_present"]:
        (hook_env / "docs" / "pipeline" / ".setup-mode").write_text("")
    agent_type = case["agent_type"] or None
    r = run_hook_with_project_dir(HOOK, build_bash_input(case["command"], agent_type=agent_type), hook_env)
    assert r.returncode == case["expect_exit"], f"{case['id']}: {case['note']}. got {r.returncode}"


@pytest.mark.parametrize(
    "case", ATELIER_SETUP_MODE_ENV_CASES, ids=[c["id"] for c in ATELIER_SETUP_MODE_ENV_CASES]
)
def test_portal_atelier_setup_mode_env_case(hook_env, case):
    agent_type = case["agent_type"] or None
    r = run_hook(
        HOOK,
        build_bash_input(case["command"], agent_type=agent_type),
        hook_env,
        env_override={"ATELIER_SETUP_MODE": case["atelier_setup_mode"]},
    )
    assert r.returncode == case["expect_exit"], f"{case['id']}: {case['note']}. got {r.returncode}"


@pytest.mark.parametrize("case", TOOL_NAME_CASES, ids=[c["id"] for c in TOOL_NAME_CASES])
def test_portal_tool_name_case(hook_env, case):
    agent_type = case["agent_type"] or None
    d = {"tool_name": case["tool_name"], "tool_input": {"command": case["command"]}}
    if agent_type is not None:
        d["agent_type"] = agent_type
    r = run_hook(HOOK, json.dumps(d, separators=(",", ":")), hook_env)
    assert r.returncode == case["expect_exit"], f"{case['id']}: {case['note']}. got {r.returncode}"


@pytest.mark.parametrize("case", GIT_AVAILABLE_CASES, ids=[c["id"] for c in GIT_AVAILABLE_CASES])
def test_portal_git_available_case(hook_env, case):
    (hook_env / ".claude").mkdir(exist_ok=True)
    config_path = hook_env / ".claude" / "pipeline-config.json"
    config_path.write_text(json.dumps({"git_available": case["git_available"]}))
    agent_type = case["agent_type"] or None
    r = run_hook(HOOK, build_bash_input(case["command"], agent_type=agent_type), hook_env)
    assert r.returncode == case["expect_exit"], f"{case['id']}: {case['note']}. got {r.returncode}"
