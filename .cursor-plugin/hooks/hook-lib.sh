#!/bin/bash
# hook-lib.sh -- Shared hook utility library (ADR-0034 Wave 2 Step 2.1)
#
# Source this file from any hook that needs the shared parsers:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   if [ -f "$SCRIPT_DIR/hook-lib.sh" ]; then
#     source "$SCRIPT_DIR/hook-lib.sh"
#   fi
#
# All functions read from stdin when they need input. Callers pipe data in:
#   echo "$INPUT" | hook_lib_get_agent_type
#   cat "$STATE_FILE" | hook_lib_pipeline_status_field phase
#
# Non-blocking by design: all functions exit 0 on parse failure and return
# empty output. Callers treat empty output as "field absent / fail-open".
# Retro lesson #003 compliant.

# ─── hook_lib_pipeline_status_field <field> ───────────────────────────────────
#
# Reads stdin, finds the PIPELINE_STATUS JSON marker, and returns the value
# of the named field. Uses jq which is brace-aware (fixes the S22 regression
# where grep -o cut off on embedded } in field values).
#
# Format expected on stdin:
#   <!-- PIPELINE_STATUS: {"phase":"build","feature":"x",...} -->
#
# Usage:
#   value=$(cat "$STATE_FILE" | hook_lib_pipeline_status_field phase)
#
# Returns empty and exits 1 when field is absent or JSON is malformed.

hook_lib_pipeline_status_field() {
  local field="$1"
  local line json value

  # Read stdin line by line; find the PIPELINE_STATUS marker line
  while IFS= read -r line; do
    if [[ "$line" == *"PIPELINE_STATUS: {"* ]]; then
      # Strip everything before the opening { of the JSON object
      json="${line#*PIPELINE_STATUS: }"
      # Strip the trailing HTML comment suffix --> (and any whitespace)
      json="${json% -->}"
      # Also strip bare --> without leading space (avoids quoting issue with }
      # inside the parameter expansion by using a variable for the suffix)
      _suffix='-->'
      json="${json%"$_suffix"}"
      break
    fi
  done

  [ -z "$json" ] && return 1

  value=$(printf '%s' "$json" | jq -r --arg f "$field" '.[$f] // empty' 2>/dev/null) || return 1
  [ -z "$value" ] && return 1
  printf '%s\n' "$value"
}

# ─── hook_lib_json_escape ─────────────────────────────────────────────────────
#
# Reads a raw string from stdin and outputs a valid JSON string literal
# (including the surrounding double-quotes). Uses jq -Rs to handle all
# special characters: newlines, tabs, backslashes, quotes, unicode.
#
# This replaces the broken sed-based json_escape in session-boot.sh (S22).
#
# Usage:
#   escaped=$(printf '%s' "$value" | hook_lib_json_escape)
#
# The output is a complete JSON string literal, e.g.: "line1\nline2"

hook_lib_json_escape() {
  jq -Rs '.' 2>/dev/null
}

# ─── hook_lib_get_agent_type ──────────────────────────────────────────────────
#
# Reads JSON from stdin, returns the agent type string.
# Priority: .agent_type (top-level) > .tool_input.subagent_type
# Returns empty string when neither field is present.
#
# Usage:
#   agent=$(echo "$INPUT" | hook_lib_get_agent_type)

hook_lib_get_agent_type() {
  jq -r '.agent_type // .tool_input.subagent_type // empty' 2>/dev/null
}

# ─── hook_lib_agent_type_matches <agent_type> <base_type...> ─────────────────
#
# Returns 0 (true) when $agent_type is exactly one of the given base types,
# OR begins with "<base_type>-" (a named Agent-tool instance, e.g. Eva
# invoking Agent({name: "colby-u10-tiebreak", subagent_type: "colby"})).
#
# Why this exists: .agent_type holds the registered subagent_type for a plain
# subagent ("colby"), but the instance NAME for a named teammate spawn
# ("colby-u10-tiebreak") in an interactive session with agent teams on
# (probed on CLI 2.1.280). A bare-string match (`"$AGENT_TYPE" = colby`)
# misses every named instance. The explicit-hyphen prefix check restores the
# match without widening it to unrelated names that share a leading
# substring: base "colby" matches "colby" and "colby-*", never "colbyalt".
#
# NOTE: this is a naming-convention match, not a true subagent_type
# resolution. It cannot know that "poirot-*" instances run as subagent_type
# "investigator" -- callers that allowlist Poirot must list both
# "investigator" and "poirot" among the base types.
#
# Usage:
#   if hook_lib_agent_type_matches "$AGENT_TYPE" sarah colby agatha robert \
#        robert-spec sable sable-ux ellis; then ... fi

hook_lib_agent_type_matches() {
  local agent_type="$1"
  shift
  local base
  for base in "$@"; do
    if [ "$agent_type" = "$base" ] || [[ "$agent_type" == "$base"-* ]]; then
      return 0
    fi
  done
  return 1
}

# ─── hook_lib_agent_base_type <agent_type> <base_type...> ────────────────────
#
# Echoes the base type that $agent_type matches under the same rule as
# hook_lib_agent_type_matches, choosing the LONGEST matching base so that
# overlapping pairs resolve to the more specific persona ("robert-spec-retro"
# -> robert-spec, not robert; "sable-ux-overlay" -> sable-ux, not sable).
# Echoes nothing and returns 1 when no base matches. Use this wherever the
# agent type is a lookup key (e.g. the ADR-0060 agent_roster), since a named
# instance is never itself a key.
#
# Usage:
#   base=$(hook_lib_agent_base_type "$AGENT_TYPE" robert robert-spec) || exit 0

hook_lib_agent_base_type() {
  local agent_type="$1"
  shift
  local base best=""
  for base in "$@"; do
    if [ "$agent_type" = "$base" ] || [[ "$agent_type" == "$base"-* ]]; then
      [ "${#base}" -gt "${#best}" ] && best="$base"
    fi
  done
  [ -n "$best" ] || return 1
  printf '%s\n' "$best"
}

# ─── hook_lib_assert_agent_type <expected> ────────────────────────────────────
#
# Reads JSON from stdin. Calls hook_lib_get_agent_type and compares to
# the expected value. Exits non-zero with a message if mismatch.
#
# Usage:
#   echo "$INPUT" | hook_lib_assert_agent_type "ellis"

hook_lib_assert_agent_type() {
  local expected="$1"
  local actual
  actual=$(hook_lib_get_agent_type)
  if [ "$actual" != "$expected" ]; then
    echo "ERROR: Expected agent_type '$expected' but got '${actual:-<empty>}'" >&2
    return 1
  fi
}

# ─── hook_lib_emit_deny <message> ─────────────────────────────────────────────
#
# Emits the standard Claude hook JSON deny response to stdout.
# Callers should exit 2 after calling this function.
#
# Usage:
#   hook_lib_emit_deny "BLOCKED: reason"
#   exit 2

hook_lib_emit_deny() {
  local message="$1"
  local escaped_message
  escaped_message=$(printf '%s' "$message" | jq -Rs '.' 2>/dev/null || printf '"%s"' "$message")
  printf '{"decision":"block","reason":%s}\n' "$escaped_message"
}

# ─── hook_lib_emit_allow ──────────────────────────────────────────────────────
#
# Emits the standard Claude hook JSON allow response to stdout.
#
# Usage:
#   hook_lib_emit_allow

hook_lib_emit_allow() {
  printf '{"decision":"allow"}\n'
}
