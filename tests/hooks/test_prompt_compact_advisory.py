"""Tests for prompt-compact-advisory.sh's Ellis identity match (G-143).

The hook used to compare agent_type to the literal string "ellis", which
silently skipped the wave-boundary advisory for every named Ellis instance
(e.g. ellis-push8). Fixed to match via hook_lib_agent_type_matches, which
also matches the "<base>-" prefix form -- see that function's header in
hook-lib.sh for why a bare-string comparison alone misses a named teammate
spawn.
"""

import json

from conftest import run_compact_advisory, write_pipeline_status


def _stop_input(agent_type: str) -> str:
    return json.dumps({"agent_type": agent_type, "agent_id": "a1", "session_id": "s1"})


def test_bare_ellis_fires_advisory(tmp_path):
    write_pipeline_status(tmp_path, '{"phase":"build"}')
    r = run_compact_advisory(_stop_input("ellis"), tmp_path)
    assert r.returncode == 0
    assert "WAVE BOUNDARY" in r.stdout


def test_named_ellis_instance_fires_advisory(tmp_path):
    """G-143 fix: a named Ellis teammate spawn (ellis-push8) must also
    trigger the advisory -- this is the case the old exact-match missed."""
    write_pipeline_status(tmp_path, '{"phase":"build"}')
    r = run_compact_advisory(_stop_input("ellis-push8"), tmp_path)
    assert r.returncode == 0
    assert "WAVE BOUNDARY" in r.stdout


def test_ellis_lookalike_does_not_fire_advisory(tmp_path):
    write_pipeline_status(tmp_path, '{"phase":"build"}')
    r = run_compact_advisory(_stop_input("ellisfoo"), tmp_path)
    assert r.returncode == 0
    assert "WAVE BOUNDARY" not in r.stdout


def test_non_ellis_agent_does_not_fire_advisory(tmp_path):
    write_pipeline_status(tmp_path, '{"phase":"build"}')
    r = run_compact_advisory(_stop_input("colby"), tmp_path)
    assert r.returncode == 0
    assert "WAVE BOUNDARY" not in r.stdout
