#!/bin/bash
# enforce-brain-capture-pending.sh -- SubagentStop hook (ADR-0053).
#
# Co-fires with log-agent-stop.sh on every SubagentStop. When the stopping
# agent is in the brain-grade allowlist, writes a pending-capture marker at
# {pipeline_state_dir}/.pending-brain-capture.json so the PreToolUse gate
# (enforce-brain-capture-gate.sh) can block Eva's next Agent invocation
# until she calls agent_capture (cleared by clear-brain-capture-pending.sh).
#
# Allowlist (mirrors the original brain-extractor `if:` clause):
#   sarah, colby, agatha, robert, robert-spec, sable, sable-ux, ellis
# Excluded (verification/investigation/scout output is logged elsewhere or
# is ephemeral): poirot, sherlock, sentinel, scout, distillator,
# brain-extractor, discovered agents, unknown.
#
# Contract: SubagentStop hooks must NEVER exit 2 -- this script exits 0
# always. Failure to write the pending file is logged to stderr but never
# blocks the agent stop.

# Do NOT use set -e -- we want to continue past write failures.
set -uo pipefail

[ "${ATELIER_SETUP_MODE:-}" = "1" ] && exit 0

PROJECT_ROOT="${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[ -f "${PROJECT_ROOT}/docs/pipeline/.setup-mode" ] && exit 0

INPUT=$(cat)

# jq missing -> fail open silently (do not block the stop).
if ! command -v jq &>/dev/null; then
  exit 0
fi

# Source shared hook library for hook_lib_get_agent_type and
# hook_lib_agent_base_type.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/hook-lib.sh" ]; then
  source "$SCRIPT_DIR/hook-lib.sh" 2>/dev/null || true
fi

# Extract agent_type. Use hook-lib if available, otherwise fall back to the
# same composite jq expression hook_lib_get_agent_type uses.
if declare -f hook_lib_get_agent_type >/dev/null 2>&1; then
  AGENT_TYPE=$(echo "$INPUT" | hook_lib_get_agent_type 2>/dev/null || true)
else
  AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // .tool_input.subagent_type // empty' 2>/dev/null || true)
fi

# Allowlist gate. Anything outside the 8 brain-grade producers exits silently.
#
# Matches bare type ("colby") AND named Agent-tool instances ("colby-u10-
# tiebreak") via hook_lib_agent_type_matches -- see that function's header in
# hook-lib.sh for why a bare-string match alone misses every named
# invocation. BASE_TYPE is the persona the instance belongs to (longest
# matching base, so "sable-ux-overlay" -> sable-ux and "robert-spec-retro" ->
# robert-spec); the roster check below keys on it, because a named instance
# is never itself an agent_roster key. The marker still records the raw
# AGENT_TYPE so Eva can see which instance stopped.
ALLOWLIST=(sarah colby agatha robert robert-spec sable sable-ux ellis)
if declare -f hook_lib_agent_base_type >/dev/null 2>&1; then
  BASE_TYPE=$(hook_lib_agent_base_type "$AGENT_TYPE" "${ALLOWLIST[@]}") || exit 0
else
  # hook-lib.sh failed to load -- fall back to the old exact-match allowlist
  # (fail-narrow: named instances won't match, same as before this fix).
  # Loud on purpose: this fallback silently restores the pre-fix bypass (named
  # instances like "colby-u10-tiebreak" never match a bare-string allowlist),
  # so a missing/unreadable hook-lib.sh must not degrade without a signal.
  echo "WARNING: enforce-brain-capture-pending.sh: hook-lib.sh unavailable -- falling back to exact-match agent_type allowlist. Named Agent-tool instances (e.g. colby-u10-tiebreak) will NOT match and will silently bypass the brain-capture gate until hook-lib.sh is restored." >&2
  case "$AGENT_TYPE" in
    sarah|colby|agatha|robert|robert-spec|sable|sable-ux|ellis) BASE_TYPE="$AGENT_TYPE" ;;
    *) exit 0 ;;
  esac
fi

# Roster intersection (ADR-0060): skip capture when the stopping agent is not
# in the active agent_roster. Fail-open when roster key is absent/malformed.
_roster_check() {
  local agent="$1"
  # Map from agent_type values used by SubagentStop to roster keys.
  # robert-spec and sable-ux are skill-activated producers -- not in the roster;
  # sable (reviewer) is always-on -- never gated by roster.
  # Treat all three as enabled so their captures are not silently dropped.
  case "$agent" in
    robert-spec|sable|sable-ux) return 0 ;;
  esac
  local roster_config
  if [ -f "${PROJECT_ROOT}/.cursor/pipeline-config.json" ]; then
    roster_config="${PROJECT_ROOT}/.cursor/pipeline-config.json"
  else
    roster_config="${PROJECT_ROOT}/.claude/pipeline-config.json"
  fi
  [ ! -f "$roster_config" ] && return 0  # fail-open: no config
  # Fail-open when agent_roster key is entirely absent (upgrade path from v5).
  local roster_present
  roster_present=$(jq -r 'if .agent_roster then "yes" else "no" end' \
    "$roster_config" 2>/dev/null) || true
  if [ "${roster_present:-no}" = "no" ]; then
    return 0  # fail-open: old install, treat all agents as enabled
  fi
  local enabled
  # Agent absent from a present roster = disabled (user didn't select it).
  enabled=$(jq -r --arg a "$agent" \
    'if .agent_roster[$a] == null then "false" elif .agent_roster[$a].enabled == false then "false" else "true" end' \
    "$roster_config" 2>/dev/null) || true
  [ "${enabled:-true}" != "false" ]
}
if ! _roster_check "$BASE_TYPE"; then
  exit 0
fi

# Resolve pipeline_state_dir from enforcement-config.json. Fail-open on a
# missing config -- this hook must never block the stop.
CONFIG="$SCRIPT_DIR/enforcement-config.json"
if [ -f "$CONFIG" ]; then
  PIPELINE_DIR=$(jq -r '.pipeline_state_dir // "docs/pipeline"' "$CONFIG" 2>/dev/null || echo "docs/pipeline")
else
  PIPELINE_DIR="docs/pipeline"
fi

# Make pipeline_state_dir an absolute path under PROJECT_ROOT when relative.
case "$PIPELINE_DIR" in
  /*) ;;
  *) PIPELINE_DIR="${PROJECT_ROOT}/${PIPELINE_DIR}" ;;
esac

mkdir -p "$PIPELINE_DIR" 2>/dev/null || {
  echo "WARNING: enforce-brain-capture-pending.sh: cannot create $PIPELINE_DIR" >&2
  exit 0
}

# Short-circuit when either sentinel is present (ADR-0055 + ADR-0053):
#   .brain-unavailable    -> brain installed but unreachable (Eva escape hatch).
#   .brain-not-installed  -> no brain plugin installed at all.
# Writing a pending file in either case would deadlock the gate, since no
# agent_capture call can reach a brain that does not exist or is down.
if [ -f "${PIPELINE_DIR}/.brain-unavailable" ] || [ -f "${PIPELINE_DIR}/.brain-not-installed" ]; then
  exit 0
fi

PENDING_FILE="${PIPELINE_DIR}/.pending-brain-capture.json"

# Pull transcript_path (best-effort; SubagentStop payload includes it on
# Claude Code, may be absent on Cursor). Empty string is fine.
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Write the pending-capture marker. Use jq to compose to guarantee valid
# JSON regardless of escapes in transcript_path.
jq -n \
  --arg agent_type "$AGENT_TYPE" \
  --arg transcript_path "$TRANSCRIPT_PATH" \
  --arg timestamp "$TIMESTAMP" \
  '{agent_type: $agent_type, transcript_path: $transcript_path, timestamp: $timestamp}' \
  > "$PENDING_FILE" 2>/dev/null || {
    echo "WARNING: enforce-brain-capture-pending.sh: failed to write $PENDING_FILE" >&2
  }

exit 0
