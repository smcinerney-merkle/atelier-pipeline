#!/bin/bash
# enforce-spawn-name.sh -- PreToolUse hook on Agent (G-142).
#
# WHY THIS EXISTS: every mechanical guard in this repo identifies an agent
# by agent_type, and for a NAMED teammate spawn, agent_type is whatever name
# the spawner chose -- not the definition it was spawned from
# (hook_lib_agent_type_matches's header explains why). Nothing in the
# Agent tool-call payload carries the definition type; a probe on CLI
# 2.1.282 confirmed a named spawn's tool_input has only `subagent_type` and
# `name`, and `customAgentType` lives only in the harness's private
# per-session meta.json, never in a hook payload. Two real incidents
# motivated this gate:
#   - A generic `claude` agent named `ellis-gd-tag` committed through the
#     Ellis-only git guard in another repo (enforce-git.sh matches on
#     agent_type, which for that spawn WAS "ellis-gd-tag").
#   - A payload named `agatha-disguised` would skip Colby's path guard and
#     inherit Agatha's write allowlist, because a name starting with a
#     different persona's write-allowlisted prefix passes any guard that
#     only checks a hyphen boundary.
#
# RULE: when a spawner passes `name`, it MUST be `<subagent_type>` or
# `<subagent_type>-<suffix>`. No `if` on this registration -- every Agent
# call is cheap to check (a handful of string comparisons), and an `if`
# conditional here would repeat the exact mistake that made enforce-git.sh's
# old registration never fire at all (G-107): the harness's `if` evaluates a
# narrow permission-rule form, not arbitrary JS, and a silently-inert gate
# is worse than an always-on cheap one.
#
# Refusals (exit 2, message on stderr):
#   1. Named spawn, no subagent_type at all -- nothing to validate the name
#      against.
#   2. Named spawn whose name is neither exactly subagent_type nor
#      "<subagent_type>-<suffix>" -- the core naming-convention violation
#      (ellis-gd-tag/claude, agatha-disguised/colby, poirot-segment/
#      investigator, colbyfoo/colby).
#   3. OVERLAP: the name's longest-matching base across {subagent_type} +
#      the known persona roster is NOT the declared subagent_type. This
#      catches a case rule 2 alone lets through: a name that satisfies the
#      hyphen-prefix check against its own declared type but ALSO matches a
#      longer, more specific persona name (robert-spec-x under subagent_type
#      robert; sable-ux-1 under subagent_type sable). Without this check a
#      read-only reviewer (robert, sable) could be spawned under a name that
#      makes it look like the producer variant (robert-spec, sable-ux) to
#      any downstream guard that keys off name -- inheriting a producer's
#      write allowlist.
#
# Unnamed spawns (no `name` key, or an empty one) are always allowed --
# nothing here narrows what an anonymous Agent call can do.
#
# Fail-CLOSED for named spawns when hook-lib.sh cannot be sourced (unlike
# most hooks in this repo, which fail open on a missing library). A gate
# whose entire job is identity verification must not silently stop
# verifying identity.

set -uo pipefail
[ "${ATELIER_SETUP_MODE:-}" = "1" ] && exit 0
[ -f "${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}/docs/pipeline/.setup-mode" ] && exit 0

INPUT=$(cat)

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required for atelier-pipeline hooks. Install: brew install jq" >&2
  exit 2
fi

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
[ "$TOOL_NAME" != "Agent" ] && exit 0

SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty' 2>/dev/null) || exit 0
SPAWN_NAME=$(echo "$INPUT" | jq -r '.tool_input.name // empty' 2>/dev/null) || exit 0

# Unnamed spawn: nothing to validate. Allow, regardless of subagent_type.
[ -z "$SPAWN_NAME" ] && exit 0

# Named spawn, no subagent_type: cannot validate a name against a type that
# was never declared.
if [ -z "$SUBAGENT_TYPE" ]; then
  echo "BLOCKED: Agent spawned with name '$SPAWN_NAME' but no subagent_type. Hooks identify a named teammate by its name, and that name must be checked against a declared subagent_type -- there is nothing to check it against here. Fix: pass subagent_type alongside name." >&2
  exit 2
fi

# Source shared hook library for hook_lib_agent_base_type / hook_lib_agent_personas.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
LIB_LOADED=0
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/hook-lib.sh" ]; then
  # shellcheck disable=SC1091
  if source "$SCRIPT_DIR/hook-lib.sh" 2>/dev/null; then
    LIB_LOADED=1
  fi
fi

if [ "$LIB_LOADED" -ne 1 ] || ! declare -f hook_lib_agent_base_type >/dev/null 2>&1 \
   || ! declare -f hook_lib_agent_personas >/dev/null 2>&1; then
  # Fail CLOSED for named spawns -- this gate's only job is identity
  # verification; a missing library must not silently widen it open.
  echo "BLOCKED: enforce-spawn-name.sh could not load hook-lib.sh, so the naming rule for named spawn '$SPAWN_NAME' (subagent_type '$SUBAGENT_TYPE') cannot be verified. Failing closed. Fix: restore .claude/hooks/hook-lib.sh." >&2
  exit 2
fi

# Rule 2: name must equal subagent_type, or start with "<subagent_type>-".
if [ "$SPAWN_NAME" != "$SUBAGENT_TYPE" ] && [[ "$SPAWN_NAME" != "$SUBAGENT_TYPE"-* ]]; then
  echo "BLOCKED: Agent spawned with name '$SPAWN_NAME' and subagent_type '$SUBAGENT_TYPE'. Hooks identify a named teammate by its name field, not its subagent_type -- every mechanical guard in this repo (the Ellis-only git guard, Colby's path guard, the brain-capture allowlist) keys off whichever value a payload carries as agent_type, and for a named spawn that is the name. A name that doesn't match its declared type lets a mismatched persona's allowlist apply to this spawn. Fix: name it '$SUBAGENT_TYPE' or '$SUBAGENT_TYPE-<suffix>', or spawn without a name." >&2
  exit 2
fi

# Rule 3 (OVERLAP): the longest-matching base across {subagent_type} plus
# the full persona roster must be exactly the declared subagent_type.
PERSONAS=($(hook_lib_agent_personas))
BASE=$(hook_lib_agent_base_type "$SPAWN_NAME" "$SUBAGENT_TYPE" "${PERSONAS[@]}") || BASE=""
if [ "$BASE" != "$SUBAGENT_TYPE" ]; then
  echo "BLOCKED: Agent spawned with name '$SPAWN_NAME' and subagent_type '$SUBAGENT_TYPE', but '$SPAWN_NAME' also matches the more specific persona '$BASE'. A named teammate's name must not embed a different, more specific persona prefix than the type it was actually spawned as -- otherwise a guard keying on name (e.g. a per-agent write allowlist) resolves to '$BASE' instead of '$SUBAGENT_TYPE'. Fix: spawn as subagent_type '$BASE', or choose a name that only matches '$SUBAGENT_TYPE'." >&2
  exit 2
fi

exit 0
