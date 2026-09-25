#!/bin/bash
# pipeline-state-path.sh -- Session state path resolver
#
# Exports two distinct functions:
#   session_state_dir()     -- in-repo, project-relative
#   error_patterns_path()   -- in-repo, unchanged (ADR-0032 Decision)
#
# ADR-0032 originally specified an out-of-repo, per-worktree directory under
# ~/.atelier/pipeline/{project-slug}/{8-char-hash}/. That directory was
# created by this function's own `mkdir -p` but never populated by any
# writer -- every reader (session-boot.sh, post-compact-reinject.sh,
# prompt-compact-advisory.sh) silently read nothing from it. Fixed 2026-09-25
# (G-151): session_state_dir() now returns {project_root}/docs/pipeline as
# the primary path -- in-repo, git-tracked, and consistent with the seven
# hooks that already resolve pipeline_state_dir via enforcement-config.json,
# and with both callers' own fallback definitions.
#
# Non-blocking: exits 0 on every error path. Falls back to docs/pipeline/
# if resolution fails. Retro lesson #003 compliant.
#
# Usage (from another script):
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/pipeline-state-path.sh"
#   STATE_DIR=$(session_state_dir)
#   ERR_PATH=$(error_patterns_path)

# ─── session_state_dir ────────────────────────────────────────────────────────
#
# Returns an absolute path of the form:
#   {project_root}/docs/pipeline
#
# Resolution order:
#   (a) CLAUDE_PROJECT_DIR env var  -- set by Claude Code
#   (b) CURSOR_PROJECT_DIR env var  -- set by Cursor
#   (c) pwd                         -- fallback to current directory (relative "docs/pipeline")
#
# On any failure (no project dir env var, unresolvable path) the function
# prints the legacy relative path docs/pipeline and exits 0 -- the caller
# gets a valid path it can still use.

session_state_dir() {
  local project_root=""

  # Resolve project root — only use the project-relative absolute path when
  # an explicit project directory env var is set. Without one, we cannot
  # distinguish a transient subprocess (e.g. a test runner with cwd=/tmp/xxx)
  # from a real worktree, so we fall back to the legacy relative path.
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    project_root="$CLAUDE_PROJECT_DIR"
  elif [ -n "${CURSOR_PROJECT_DIR:-}" ]; then
    project_root="$CURSOR_PROJECT_DIR"
  else
    # No explicit project env var — use the legacy relative path so callers
    # reading docs/pipeline/ relative to cwd continue to work correctly.
    echo "docs/pipeline"
    return 0
  fi

  # Resolve absolute path
  project_root="$(cd "$project_root" 2>/dev/null && pwd)" || {
    echo "docs/pipeline"
    return 0
  }

  echo "$project_root/docs/pipeline"
  return 0
}

# ─── error_patterns_path ──────────────────────────────────────────────────────
#
# Returns the in-repo path for error-patterns.md.
# Per ADR-0032 Decision: error-patterns.md stays in-repo so it can be committed
# and shared with the team. It is NOT per-worktree.
#
# Returns a relative path (docs/pipeline/error-patterns.md) so callers work
# correctly regardless of current working directory, consistent with the
# legacy behaviour session-boot.sh had before this helper was introduced.

error_patterns_path() {
  echo "docs/pipeline/error-patterns.md"
  return 0
}
