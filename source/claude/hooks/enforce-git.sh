#!/bin/bash
# Phase 2 supplement: Prevent unauthorized agents from running git write operations or test suites
# PreToolUse hook on Bash
#
# G-107 / G-143: settings.json used to register this hook with an `if`
# conditional (`tool_input.command.includes('git ')`) written as a JS
# expression. The harness's `if` evaluates a narrow permission-rule form,
# not arbitrary JS, so the conditional never matched and this script never
# ran at all -- an install-wide silent no-op. The `if` has been removed from
# every settings.json / hooks.md registration copy; this script now runs on
# every Bash call and relies entirely on its own internal filtering (the
# empty TOOL_NAME / COMMAND checks below) to stay cheap on non-git calls.
#
# Git write operations (add, commit, push, reset, destructive checkout,
# restore, clean) are allowed ONLY for Ellis (bare `ellis` or a named
# instance, matched via hook_lib_agent_type_matches -- see that function's
# header in hook-lib.sh for why a bare-string match alone misses a named
# teammate spawn). All other agents and the main thread (Eva) are blocked.
#
# Test suite execution is allowed for Colby, Poirot (matched on `investigator`
# or `poirot`, since Poirot's registered subagent_type is `investigator` --
# hook_lib_agent_type_matches's NOTE explains why callers must list both),
# and the main thread (Eva -- empty agent_type). See the gate below for why
# the main thread is deliberately permitted here.

set -euo pipefail
[ "${ATELIER_SETUP_MODE:-}" = "1" ] && exit 0
[ -f "${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}/docs/pipeline/.setup-mode" ] && exit 0

INPUT=$(cat)

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required for atelier-pipeline hooks. Install: brew install jq" >&2
  exit 2
fi

# Source shared hook library (ADR-0034 Wave 2 Step 2.1)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/hook-lib.sh" ]; then
  source "$SCRIPT_DIR/hook-lib.sh" 2>/dev/null || true
fi

# Local fallback for hook_lib_agent_type_matches -- guards this call under
# `set -e` when hook-lib.sh fails to load (a "command not found" on an
# unset function would otherwise abort the whole script under `set -e`,
# which would fail this backstop OPEN on every Bash call). Same semantics
# as hook-lib.sh's version: exact match, or a "<base>-" prefix.
_agent_matches() {
  if declare -f hook_lib_agent_type_matches >/dev/null 2>&1; then
    hook_lib_agent_type_matches "$@"
    return $?
  fi
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

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty') || exit 0
[ "$TOOL_NAME" != "Bash" ] && exit 0

AGENT_TYPE=$(echo "$INPUT" | hook_lib_get_agent_type 2>/dev/null || echo "$INPUT" | jq -r '.agent_type // .tool_input.subagent_type // empty' 2>/dev/null || true)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty') || exit 0
[ -z "$COMMAND" ] && exit 0

# No-op when git is not available
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}}"
# Try .cursor/ first (Cursor), fall back to .claude/ (Claude Code)
if [ -f "${PROJECT_ROOT}/.cursor/pipeline-config.json" ]; then
  CONFIG_FILE="${PROJECT_ROOT}/.cursor/pipeline-config.json"
else
  CONFIG_FILE="${PROJECT_ROOT}/.claude/pipeline-config.json"
fi
if [ -f "$CONFIG_FILE" ]; then
  GIT_AVAILABLE=$(jq -r 'if .git_available == false then "false" else "true" end' "$CONFIG_FILE" 2>/dev/null) || true
  if [ "$GIT_AVAILABLE" = "false" ]; then
    exit 0
  fi
fi

# Block git write operations -- only Ellis is allowed.
# Allow git status, git diff, git log, git branch (read-only git operations) for everyone
#
# The pattern is anchored to command position (start, &&, ||, ;, |, newline,
# or an opening parenthesis) and scopes \b inside the word-verb group. The
# checkout branch closes every destructive form: "checkout -- <paths>",
# "checkout <ref> -- <paths>", "checkout ." and any short-flag cluster
# containing f ("-f", "-fq", "-qf"). Long options (--force, --ours, --theirs,
# --patch, --detach) begin with "--" and are caught by the same branch.
# Known false positive: the "\(" anchor also fires on a parenthesis inside a
# quoted string (e.g. echo "(git add later)").
#
# Identity: ellis or a named Ellis instance (ellis-*), via
# hook_lib_agent_type_matches (see hook-lib.sh header) since agent_type
# holds the instance name for named teammate spawns.
if echo "$COMMAND" | grep -qE '(^|&&|\|\||;|\||\n|\()\s*git\s+((add|commit|push|reset|restore|clean)\b|checkout\s+([^[:space:]]+\s+)?(--|-[a-zA-Z]*f|\.(\s|$)))' 2>/dev/null; then
  if _agent_matches "$AGENT_TYPE" ellis; then
    exit 0
  fi
  echo "BLOCKED: Only Ellis can run git write operations. Route commits through Ellis. Allowed for all: git status, git diff, git log, git branch." >&2
  exit 2
fi

# NOTE (ADR-0038): git worktree add/remove are intentionally NOT blocked.
# Eva creates worktrees at pipeline start for session isolation.
# Do NOT add 'worktree' to the blocked operations regex above.

# Block test execution -- allowed for Colby, Poirot, and the main thread
# (Eva). Colby and Poirot are matched via hook_lib_agent_type_matches (a
# named instance like colby-g107 or poirot-segment qualifies); Poirot's
# registered subagent_type is `investigator`, so both `investigator` and
# `poirot` are listed as bases per the NOTE in hook_lib_agent_type_matches.
# The main thread has an empty AGENT_TYPE and is deliberately permitted:
# pipeline-orchestration.md's mandatory gates require Eva to run the
# project's test command directly via Bash between work units and at wave
# boundaries, and those behavioral rules are the primary constraint -- this
# hook is the mechanical backstop, not a stricter rule that overrides them.
#
# The anchor (^|&&|\|\||;|\||\n)\s* ensures we only match test runners that are
# actually being invoked as commands, not referenced as string values inside echo,
# variable assignments, or installation scripts. Without the anchor, a command like
# `echo "run pytest to verify"` would produce a false positive and block Eva from
# running diagnostic scripts that mention test tool names.
#
# G-143 (ported from RF's G-111/G-112): the pattern previously matched
# `(npm|yarn|pnpm)\s+test\b` only, which cannot match a `run` subcommand at
# all -- `npm run test:run` and `npm run test:e2e` LEAKED past the gate for
# every non-allowlisted agent. Separately, the command-position anchor
# required the runner name immediately after start-of-line/&&/;/|/(, so an
# `npx `/`pnpm exec `/`yarn exec ` invoker prefix defeated it: `npx vitest
# run` and `npx jest` also LEAKED, as did `npx playwright test`. Fixed by
# (a) adding an `(npm|yarn|pnpm)\s+(run\s+)?test(:\S+)?\b` branch that covers
# both the bare-script and `run <script>` forms, matching any script name
# that starts with `test` (`test`, `test:run`, `test:e2e`, `test:coverage`
# all match; `lint`, `build`, `db:migrate` do not); and (b) adding an
# optional `(npx|pnpm\s+exec|yarn\s+exec)\s+` invoker-prefix group ahead of
# the bare-runner-name alternatives and a separate `playwright\s+test\b`
# alternative (playwright's other subcommands -- install, codegen,
# show-report -- are not test execution and stay allowed).
if echo "$COMMAND" | grep -qE "(^|&&|\|\||;|\||\n|\()\s*(npx|pnpm\s+exec|yarn\s+exec)?\s*(bats|pytest|jest|vitest|mocha|rspec|phpunit)\b|(^|&&|\|\||;|\||\n|\()\s*(npx|pnpm\s+exec|yarn\s+exec)?\s*playwright\s+test\b|(^|&&|\|\||;|\||\n|\()\s*(npm|yarn|pnpm)\s+(run\s+)?test(:\S+)?\b|(^|&&|\|\||;|\||\n|\()\s*node\s+--test\b|(^|&&|\|\||;|\||\n|\()\s*(go|cargo|make|dotnet|gradle|mvn)\s+test\b" 2>/dev/null; then
  if _agent_matches "$AGENT_TYPE" colby investigator poirot || [ -z "$AGENT_TYPE" ]; then
    exit 0
  fi
  echo "BLOCKED: Only Colby, Poirot, and the main thread (Eva) can run test suites. Route QA verification through Poirot." >&2
  exit 2
fi

# Note: Both blocks above are defense-in-depth. They catch direct invocations
# of git/test commands but can be bypassed via indirection (bash -c, env, wrapper
# scripts). The behavioral rules in pipeline-orchestration.md are the primary
# constraint; these hooks are the mechanical backstop.
# agent_type comes from the subagent's frontmatter name field (or the Agent
# tool's `name`, for a named teammate spawn); empty for the main thread (Eva).
exit 0
