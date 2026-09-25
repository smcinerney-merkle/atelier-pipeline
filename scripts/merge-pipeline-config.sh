#!/usr/bin/env bash
# Merges template-only top-level keys into an existing pipeline-config.json
# without ever changing a key the installed file already has. This is the
# pipeline-config.json counterpart to the enforcement-config.json merge
# documented in skills/pipeline-setup/hooks.md ("Preserve an existing
# enforcement-config.json") -- same `jq -s '.[0] + .[1]'` mechanism,
# right-hand side (installed) wins, one-line outcome report, malformed JSON
# left untouched with a warning.
#
# Usage: scripts/merge-pipeline-config.sh <template-path> <installed-path>
#
# Rules (G-151 note item 8, operator decision 2026-09-25):
#   - Only top-level keys present in the template but absent from the
#     installed file are added, using the template's value.
#   - Any key already present in the installed file is left byte-for-byte
#     unchanged, even if its value differs from the template or is empty.
#   - `agent_roster` is NEVER added by this script, even when the template
#     has it and the installed file lacks it. Its absence is the ADR-0060
#     signal the setup skill's Step 1f roster questions read to decide
#     whether to ask those questions -- silently adding the key here would
#     defeat that check on every re-run.
#   - Malformed JSON in the installed file is left untouched; the script
#     warns and exits 0 (non-blocking -- matches the enforcement-config.json
#     contract, does not fail the setup skill).
#   - This script only merges into an EXISTING installed file. A fresh
#     install (no installed file yet) is the setup skill's plain copy-the-
#     template path, unrelated to this script.
#
# Called by the pipeline-setup skill's Step 3 (state file guard), AFTER all
# interactive setup steps -- in particular Step 1f's existing-agent_roster
# detection -- have already run and already read the pre-merge file.

set -euo pipefail

TEMPLATE="${1:?Usage: scripts/merge-pipeline-config.sh <template-path> <installed-path>}"
INSTALLED="${2:?Usage: scripts/merge-pipeline-config.sh <template-path> <installed-path>}"

if [ ! -f "$TEMPLATE" ]; then
  echo "error: template not found: $TEMPLATE" >&2
  exit 1
fi

if [ ! -f "$INSTALLED" ]; then
  echo "error: installed file not found: $INSTALLED (this script only merges into an existing file -- fresh installs copy the template directly)" >&2
  exit 1
fi

if ! jq empty "$INSTALLED" >/dev/null 2>&1; then
  echo "WARNING: $INSTALLED is not valid JSON -- left unchanged. Fix it by hand, then re-run /pipeline-setup."
  exit 0
fi

# Keys the template has that the installed file lacks, with agent_roster
# excluded from consideration entirely -- it is never a candidate to add.
ADDED=$(jq -r -s '((.[0] | keys) - (.[1] | keys)) - ["agent_roster"] | .[]' "$TEMPLATE" "$INSTALLED")

if [ -z "$ADDED" ]; then
  echo "pipeline-config.json preserved; no keys added."
  exit 0
fi

# Right-hand side wins: every existing key keeps its installed value.
# `del(.agent_roster)` on the template side is load-bearing, not redundant
# with the ADDED filter above -- without it, jq's `+` would still splice
# agent_roster in whole from the template whenever the installed file lacks
# it, regardless of what the report line says.
jq -s '(.[0] | del(.agent_roster)) + .[1]' "$TEMPLATE" "$INSTALLED" > "$INSTALLED.tmp" \
  && mv "$INSTALLED.tmp" "$INSTALLED"

ADDED_LIST=$(echo "$ADDED" | paste -sd ',' - | sed 's/,/, /g')
echo "pipeline-config.json preserved; added missing keys: ${ADDED_LIST}."
