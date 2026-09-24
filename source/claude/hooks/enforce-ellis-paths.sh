#!/bin/bash
# Per-agent path enforcement: Ellis
# PreToolUse hook on Write|Edit|MultiEdit -- Ellis can only write to commit/changelog targets
# Note: ADR-0022 R20 originally stated "no path hooks for Ellis."
# ADR-0035 supersedes that decision. This hook is a safety net for
# commit-related paths. Layer 3 sequencing is the primary control.
set -uo pipefail
[ "${ATELIER_SETUP_MODE:-}" = "1" ] && exit 0
[ -f "${CLAUDE_PROJECT_DIR:-.}/docs/pipeline/.setup-mode" ] && exit 0

INPUT=$(cat)
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required for atelier-pipeline hooks. Install: brew install jq" >&2
  exit 2
fi

# Source shared hook library for the self-gate below (hook_lib_agent_type_matches).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/hook-lib.sh" ]; then
  source "$SCRIPT_DIR/hook-lib.sh" 2>/dev/null || true
fi

# Self-gate: this hook enforces Ellis's paths only. It is registered both in
# the agent's frontmatter and in settings.json (so it also sees every other
# agent and the main thread). `agent_type` holds the registered type for a
# plain subagent ("ellis") and the instance name for a named teammate spawn
# ("ellis-cardfix") -- see hook_lib_agent_type_matches in hook-lib.sh. Any
# other agent (or Eva's main thread, where agent_type is empty) exits 0 here
# -- this guard is not theirs to enforce.
if declare -f hook_lib_get_agent_type >/dev/null 2>&1; then
  AGENT_TYPE=$(echo "$INPUT" | hook_lib_get_agent_type 2>/dev/null || true)
else
  AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // .tool_input.subagent_type // empty' 2>/dev/null || true)
fi

if declare -f hook_lib_agent_type_matches >/dev/null 2>&1; then
  hook_lib_agent_type_matches "$AGENT_TYPE" ellis || exit 0
else
  # hook-lib.sh failed to load -- fall back to exact match (fail-narrow:
  # named instances like "ellis-cardfix" won't match and this guard will
  # silently NOT fire for them until hook-lib.sh is restored). Loud on
  # purpose: a missing/unreadable hook-lib.sh must not degrade silently.
  echo "WARNING: enforce-ellis-paths.sh: hook-lib.sh unavailable -- falling back to exact-match agent_type check ('$AGENT_TYPE' vs 'ellis'). Named Agent-tool instances (e.g. ellis-cardfix) will NOT match and this guard will not fire for them until hook-lib.sh is restored." >&2
  case "$AGENT_TYPE" in
    ellis) ;;
    *) exit 0 ;;
  esac
fi

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
case "$TOOL_NAME" in Write|Edit|MultiEdit) ;; *) exit 0 ;; esac

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE_PATH" ] && exit 0

# Normalize absolute paths to project-relative (Windows-compatible)
PROJECT_ROOT="${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}"
# Normalize path separators for Windows compatibility
FILE_PATH="${FILE_PATH//\\//}"
PROJECT_ROOT="${PROJECT_ROOT//\\//}"
# Case-insensitive strip to handle Windows drive letter casing (C: vs c:)
FILE_PATH_LOWER="$(echo "$FILE_PATH" | tr '[:upper:]' '[:lower:]')"
PROJECT_ROOT_LOWER="$(echo "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]')"
if [[ "$FILE_PATH_LOWER" == "${PROJECT_ROOT_LOWER}/"* ]]; then
  FILE_PATH="${FILE_PATH:${#PROJECT_ROOT}+1}"
fi

# If still absolute after normalization, it's outside the project root
if [[ "$FILE_PATH" == /* ]] || [[ "$FILE_PATH" =~ ^[A-Za-z]:/ ]]; then
  echo "BLOCKED: File is outside the project root. Attempted: $FILE_PATH" >&2
  exit 2
fi

# Reject path traversal
[[ "$FILE_PATH" == *..* ]] && { echo "BLOCKED: Path traversal detected in $FILE_PATH" >&2; exit 2; }

# Pipeline state directory: per-agent report allowlist, deny by default.
# Eva owns this directory -- pipeline-state.md, context-brief.md,
# error-patterns.md and investigation-ledger.md are hers alone (see
# default-persona.md). Ellis may write here ONLY its own report files, as
# direct children of the state directory: last-commit-*.md, last-push*.md.
# These prefixes are the ones Eva names in each invocation's <output> (the
# practice this was ported from); ellis.md's <output> contract names the
# same prefixes, and a parity test keeps the two in step. Everything else
# under the state dir -- Eva's files, a sibling agent's report,
# last-qa-report.md, last-case-file.md -- exits 2 here.
# The */* arm must stay first: in a bash case pattern "*" also matches "/",
# so last-commit-*.md alone would admit a nested path such as
# last-commit-x/pipeline-state.md.
# The location is read from enforcement-config.json (fallback
# docs/pipeline). Runs after the traversal check above, so a ".." path is
# rejected even if it would resolve inside the state directory.
CONFIG="$SCRIPT_DIR/enforcement-config.json"
PIPELINE_STATE_DIR="docs/pipeline"
if [ -f "$CONFIG" ]; then
  CONFIGURED_DIR=$(jq -r '.pipeline_state_dir // empty' "$CONFIG" 2>/dev/null)
  [ -n "$CONFIGURED_DIR" ] && PIPELINE_STATE_DIR="${CONFIGURED_DIR%/}"
fi
case "$FILE_PATH" in
  "$PIPELINE_STATE_DIR"/*)
    case "${FILE_PATH#"$PIPELINE_STATE_DIR"/}" in
      */*) ;;
      last-commit-*.md|last-push*.md) exit 0 ;;
    esac
    echo "BLOCKED: Ellis may write under $PIPELINE_STATE_DIR/ only its own reports ($PIPELINE_STATE_DIR/last-commit-*.md, $PIPELINE_STATE_DIR/last-push*.md), as direct children. The rest of the state directory is Eva's. Attempted: $FILE_PATH" >&2
    exit 2
    ;;
esac

# Ellis allowlist: changelog, git config files, and CI/CD/infra paths
case "$FILE_PATH" in
  CHANGELOG.md)          exit 0 ;;
  .gitignore)            exit 0 ;;
  .gitattributes)        exit 0 ;;
  .gitmodules)           exit 0 ;;
  .github/*)             exit 0 ;;
  .gitlab-ci.yml)        exit 0 ;;
  .gitlab-ci/*)          exit 0 ;;
  .gitlab/*)             exit 0 ;;
  .circleci/*)           exit 0 ;;
  Jenkinsfile*)          exit 0 ;;
  Dockerfile*)           exit 0 ;;
  docker-compose*)       exit 0 ;;
  deploy/*)              exit 0 ;;
  infra/*)               exit 0 ;;
  terraform/*)           exit 0 ;;
  pulumi/*)              exit 0 ;;
  k8s/*)                 exit 0 ;;
  kubernetes/*)          exit 0 ;;
esac

echo "BLOCKED: Ellis can only write to $PIPELINE_STATE_DIR/last-commit-*.md, $PIPELINE_STATE_DIR/last-push*.md, CHANGELOG.md, git config files (.gitignore, .gitattributes, .gitmodules), and CI/CD paths (.github/, .gitlab*, .circleci/, Jenkinsfile*, Dockerfile*, docker-compose*, deploy/, infra/, terraform/, pulumi/, k8s/, kubernetes/). Attempted: $FILE_PATH" >&2
exit 2
