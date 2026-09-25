"""Tests for prompt-eva-path-reminder.sh (PreToolUse hook on Write|Edit|MultiEdit).

G-151 fix: the script's main-thread/subagent guard read `.agent_id`, a field
populated on SubagentStart/Stop payloads, not PreToolUse -- reading it here
always returned empty, so the reminder fired for subagents too even when
enforce-eva-paths.sh, given the same payload, exits 0 and permits the write.
Fixed to read `.agent_type // .tool_input.subagent_type`, matching
hook_lib_get_agent_type's priority order (hook-lib.sh).
"""

from conftest import build_tool_input, run_hook_with_project_dir

HOOK = "prompt-eva-path-reminder.sh"

OUTSIDE_PATH = "src/foo.py"  # outside docs/pipeline/, relative to project root


def test_G_151_fires_for_main_thread_eva(hook_env):
    """No agent_type at all (main thread / Eva) -- reminder fires for a
    Write outside docs/pipeline/."""
    inp = build_tool_input("Write", OUTSIDE_PATH)
    r = run_hook_with_project_dir(HOOK, inp, hook_env)
    assert r.returncode == 0
    assert "[eva-path-reminder]" in r.stdout


def test_G_151_silent_for_subagent_via_agent_type(hook_env):
    """agent_type set (subagent, e.g. colby) -- reminder must stay silent.
    Before the fix this fired anyway because .agent_id is never populated
    on a PreToolUse payload."""
    inp = build_tool_input("Write", OUTSIDE_PATH, agent_type="colby")
    r = run_hook_with_project_dir(HOOK, inp, hook_env)
    assert r.returncode == 0
    assert "[eva-path-reminder]" not in r.stdout


def test_G_151_silent_for_subagent_via_tool_input_subagent_type(hook_env):
    """Fallback field .tool_input.subagent_type (some payload shapes carry
    the subagent type there instead of top-level agent_type) also silences
    the reminder."""
    inp = (
        '{"tool_name":"Write","tool_input":{"file_path":"' + OUTSIDE_PATH + '","subagent_type":"colby"}}'
    )
    r = run_hook_with_project_dir(HOOK, inp, hook_env)
    assert r.returncode == 0
    assert "[eva-path-reminder]" not in r.stdout


def test_G_151_silent_for_path_inside_pipeline_state_dir(hook_env):
    """Main thread, but the path is already inside docs/pipeline/ -- Eva's
    allowed zone, so no reminder is needed regardless of agent_type."""
    inp = build_tool_input("Write", "docs/pipeline/pipeline-state.md")
    r = run_hook_with_project_dir(HOOK, inp, hook_env)
    assert r.returncode == 0
    assert "[eva-path-reminder]" not in r.stdout
