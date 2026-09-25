#!/bin/bash
# Phase 2 supplement: Prevent unauthorized agents from running git write operations
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
# restore, clean, and the wider verb list below) are allowed ONLY for Ellis
# (bare `ellis` or a named instance, matched via hook_lib_agent_type_matches
# -- see that function's header in hook-lib.sh for why a bare-string match
# alone misses a named teammate spawn). All other agents and the main thread
# (Eva) are blocked.
#
# G-151 (2026-09-25, operator decision): the test-suite execution guard that
# used to live below the git-write block has been DELETED outright, not
# narrowed. Running test runners (pytest, jest, vitest, npm test, etc.) is
# now allowed for every agent and the main thread -- there is no identity
# check left to bypass. This closes G-107 (the guard's `if` never fired to
# begin with), G-112 (the npx/pnpm-exec/`npm run test:*` coverage gaps in
# the old regex) and G-114 (the main-thread/Poirot identity gaps in the old
# allowlist) by removing the code those gaps lived in.

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
# Allow git status, git diff, git log, git branch, git fetch, git show
# (read-only git operations) for everyone.
#
# G-147 (union of this fork's guard with the-guru's 6a996d3/40745cf/73107d0):
# the anchor now covers command position at start, a run of one or more of
# ; & | -- which also models bare &, |& , and ;; -- newline, or an opening
# parenthesis (so both `if true; then git commit; fi` and `(git commit)` are
# caught), and tolerates an optional then/do/else/elif shell keyword right
# before the verb. Between `git` and the verb, a run of NAMED git global
# options (GIT_GLOBAL_OPT below) is tolerated, closing the `git -C . commit`
# / `git -c user.name=x commit` bypass.
#
# G-151 (2026-09-25, operator decision, portal reconciliation): the
# position anchor and the verb alternation below are ported wholesale from
# strategy_workbench_portal's enforce-git.sh (its 140-case regression corpus
# replays 140/140 against this guard) -- they close four gaps this fork's
# 5.2.3 anchor/verb-list left open, each measured live before this change:
#  - a `{ ...; }` brace group defeated the old anchor (`{ git commit; }`
#    returned rc 0);
#  - `git gc`, `git prune`, `git reflog expire`/`delete`, `git filter-branch`
#    and `git filter-repo` were not blocked verbs at all (each returned
#    rc 0 for a non-Ellis agent, each one capable of destroying unreachable
#    or rewritten history permanently);
#  - `$(git gc --prune=now)` (command substitution) defeated the old
#    anchor;
#  - a git-shaped MENTION inside a quoted grep/awk/echo argument
#    (`grep -E "^(git commit|x)"`, `echo "; git push"`, `echo "x && git
#    commit"`) was wrongly BLOCKED by the old anchor's bare `\(` / `;&|`
#    alternatives, which had no quote-awareness at all.
# The one documented, ACCEPTED residual this ports along with the fix: a
# quoted string containing a SPACE immediately before an open paren
# (`grep -E " (git push)"`) is still indistinguishable from real command
# position without quote-tracking, and is still blocked -- same tradeoff
# the portal itself makes, not a new gap this change introduces.
#
# `checkout` and `switch` sit in the same unconditional verb alternation as
# every other write verb below (per the portal, and per this fork's own
# ADR: "unconditional per ADR, undecidable by argument-sniffing" -- a
# checkout/switch positional operand can be a path OR a ref and the two are
# not reliably distinguishable by regex). The GIT_WRITE_EXEMPT check further
# down runs FIRST and carves out the narrow flag-led forms that are safe
# non-destructive branch operations (see that block's own header for the
# exact list and the G-151/P2 policy this implements).
#
# `stash` and `reflog` are NOT plain verbs in the alternation -- each is
# individually discriminated into its write subforms (stash: bare/flagged/
# push/save/apply/pop/drop/clear/store/create/branch; reflog: expire/
# delete) so that `stash list`, `stash show ...` (any trailing form -- see
# G-151/P4 below) and bare/`reflog show`/`reflog --all` fall through
# unmatched and stay allowed for everyone, without needing an entry in
# GIT_WRITE_EXEMPT at all.
#
# G-151/P1 (operator decision 2026-09-25): `merge` (including `merge
# --ff-only`) is now an ordinary unconditional verb in the alternation --
# the fork's own earlier GIT_WRITE_EXEMPT allowance for `merge --ff-only`
# is REMOVED. A fast-forward merge still moves a branch ref; branch-
# lifecycle.md's Ellis fast-forward-merge step (`git checkout main && git
# merge --ff-only session/<id>`) stays available to Ellis only, via the
# identity check below, same as every other write verb.
GIT_SHELL_WORD="(\"[^\"]*\"|'[^']*'|\\\\.|[^[:space:]\"'\\])+"
GIT_GLOBAL_OPT="(-C[[:space:]]+${GIT_SHELL_WORD}|-c[[:space:]]+${GIT_SHELL_WORD}|--(git-dir|work-tree|namespace|attr-source|config-env)([[:space:]]+${GIT_SHELL_WORD}|=${GIT_SHELL_WORD}|=)|-[^[:space:]]+)"
#
# Known residuals (post-blind-review, fifth pass; operator decision
# 2026-09-25: documented, not fixed). GIT_SHELL_WORD does not parse a shell
# word's own internal escaping or extend across a literal newline, so two
# narrower bypasses remain --
#
#  R1: an escaped quote INSIDE a quoted run. The double-quoted alternative
#      (`"[^"]*"`) stops at the first unescaped `"`, so it cannot span a
#      `\"` embedded inside the quotes; `git -c user.name="A \" B" commit`
#      returns rc 0 for colby -- the quoted-segment alternative closes at
#      `A \` and the rest is absorbed by the generic non-space-run
#      alternative, still stopping short of the verb.
#  R2: a literal NEWLINE inside a quoted option value. This hook's matching
#      is line-oriented throughout, so a real newline inside `"[^"]*"` is
#      invisible to the regex the same way it is to `grep -q`'s per-line
#      anchors; `git -c user.name="A<LF>B" commit` (an actual newline in the
#      command string, not the two-character `\n`) returns rc 0 for colby.
#
# Both were confirmed live against this guard (`printf '%s\n' <payload> |
# env -u ATELIER_SETUP_MODE /bin/bash source/claude/hooks/enforce-git.sh`)
# and are NOT regressions -- both also return rc 0 for colby against the
# unmodified 5.2.2/5.2.3 guard and against the-guru's guard.
#
# GIT_WRITE_EXEMPT (G-151/P2, operator decision 2026-09-25): checked BEFORE
# the main write-verb match. Two subcommand shapes are exempt:
#
#  1. `checkout` LED by exactly one of -b, -t, --track, --detach, --help --
#     the narrow set of non-destructive branch operations named by the
#     operator. Any other leading token (a bare positional operand -- a
#     path, a ref, a branch name -- OR any other flag, e.g. -q) is NOT
#     exempt and falls through to the unconditional checkout block. This
#     REVERSES this fork's 5.2.3 behavior, which allowed `git checkout
#     <branch>` as a plain positional branch switch: per operator decision,
#     a checkout positional operand is undecidable by argument-sniffing
#     (it can be a path or a ref), so every such form -- `./x`, `src/app.ts`,
#     `main`, `feature/foo`, `HEAD file.txt`, `main src/x.ts`, `-q HEAD
#     file.txt`, and any of those with a trailing shell operator (`main &&
#     echo`) -- is now blocked for non-Ellis agents.
#  2. `switch` with NO required leading flag -- plain `git switch <branch>`
#     stays allowed (unlike checkout, switch's own ADR-0038-adjacent design
#     intent is to be the safe replacement for a branch-only checkout).
#     `switch` is ALSO exempt when led by exactly one of -c, --create,
#     --detach (operator decision 2026-09-25, post-5.2.3 fix): these are the
#     non-destructive counterparts of the checkout forms already kept
#     allowed above, and the operator is redirecting agents to `git switch`
#     as the checkout replacement -- `switch -c <new> [<start-point>]`,
#     `switch --create <new> [<start-point>]` and `switch --detach [<ref>]`
#     all exit 0 for every agent now, matching `switch <branch>`'s existing
#     allowance. `switch -f`, `switch --force`, `switch --discard-changes`,
#     `switch -C`/`switch --force-create`, `switch -m`/`switch --merge` and
#     `switch --orphan` are NOT exempt: none of -f/-C/-m/--orphan is in the
#     three-flag leading alternation above, and none of --force/
#     --discard-changes/--force-create/--merge is either, so each falls
#     through to the unconditional switch block. This closes G-145
#     (`switch --discard-changes` was a documented, un-fixed leak in
#     5.2.3's RF parity suite).
#
# Three properties carried over unchanged from the 5.2.2/G-147 exempt
# design, each load-bearing, each added because its absence was measured as
# a live bypass:
#
#  1. SINGLE-LINE ONLY. A command containing any NEWLINE is never exempt.
#     Fails closed.
#  2. WHOLE-STRING match against a POSITIVE trailing-argument character
#     class, not a blocklist. A trailing token's first character must come
#     from [A-Za-z0-9_/~^@:+=], OR the token is exactly a single `-` (the
#     "switch to previous branch" target -- added alongside the -c/--create/
#     --detach exemption above so `git switch -` also exits 0; this single-
#     dash alternative is intentionally exact-match only, so a multi-char
#     flag like `-f` or `-C` still fails it). Later characters in the
#     non-dash alternative may also use '-', '.', '{' or '}'. This is what
#     makes `checkout --detach -f` / `--force` / `--detach HEAD .` /
#     `--detach ./src` / `--detach ..` / `--track .` / `switch --detach "-f"`
#     (quoted -- the leading `"` isn't in the class either) correctly NOT
#     exempt (each has a trailing token starting with '-' or '.', or is
#     quoted), while `checkout --detach main`, `checkout -b feature/x
#     start-pt`, `switch main`, `switch -c new`, `switch -c new origin/x`,
#     `switch --detach main` and `switch -` ARE exempt.
#  3. Sets a FLAG -- never `exit 0`. Scopes the check to the git-write
#     block alone.
#
# G-151/P4 (operator decision 2026-09-25): `stash show` and `stash list`
# need NO entry in this exempt list at all (unlike 5.2.3, which exempted
# only a bare `stash list`/`stash show` here and left any argument on
# `show` -- `-p`, `--stat`, `.`, `stash@{n}` -- blocked by the main
# write-verb match). Per operator decision, every `stash show`/`stash list`
# form is now read-only regardless of arguments; this is implemented by
# leaving `show` and `list` OUT of the discriminated stash-write-subform
# list in the main verb alternation entirely (see above), not by widening
# an exempt allowlist here.
GIT_WRITE_EXEMPT=0
if [ "$(printf '%s' "$COMMAND" | tr -cd '\n' | wc -c | tr -d '[:space:]')" = "0" ] &&
   printf '%s' "$COMMAND" | grep -qE '^[[:space:]]*git[[:space:]]+('"$GIT_GLOBAL_OPT"'[[:space:]]+)*(checkout[[:space:]]+(-b|-t|--track|--detach|--help)|switch([[:space:]]+(-c|--create|--detach))?)([[:space:]]+(-|[A-Za-z0-9_/~^@:+=][A-Za-z0-9_/~^@:+=.{}-]*))*[[:space:]]*$'; then
  GIT_WRITE_EXEMPT=1
fi
if [ "$GIT_WRITE_EXEMPT" = "0" ] && echo "$COMMAND" | grep -qE '(^|[;&|{}]|^\(|\$\(|[;&|[:space:]]\(|\b(then|else|elif|do)\b)[[:space:]]*git[[:space:]]+('"$GIT_GLOBAL_OPT"'[[:space:]]+)*((add|commit|push|reset|restore|clean|checkout|switch|revert|rm|merge|rebase|cherry-pick|am|apply|gc|prune|filter-branch|filter-repo)([[:space:];&|)}]|$)|(stash([[:space:]]+(-[^[:space:]]+|push|save|apply|pop|drop|clear|store|create|branch)|[[:space:]]*([;&|)}]|$))|reflog[[:space:]]+(expire|delete)))' 2>/dev/null; then
  if _agent_matches "$AGENT_TYPE" ellis; then
    exit 0
  fi
  echo "BLOCKED: Only Ellis can run git write operations (add, commit, push, reset, restore, clean, stash, revert, rm, cherry-pick, rebase, apply, am, merge (incl. --ff-only), gc, prune, reflog expire/delete, filter-branch/filter-repo, and every checkout/switch form with a positional operand). Route through Ellis. Allowed for all: git status, git diff, git log, git branch, git fetch, git show, git stash list/show (any form), git reflog/reflog show, git checkout -b/-t/--track/--detach/--help, and plain non-destructive branch switching (git switch <branch>)." >&2
  exit 2
fi

# NOTE (ADR-0038): git worktree add/remove are intentionally NOT blocked.
# Eva creates worktrees at pipeline start for session isolation.
# Do NOT add 'worktree' to the blocked operations regex above.

# Note: this block is defense-in-depth. It catches direct invocations of
# git write commands but can be bypassed via indirection (bash -c, env, wrapper
# scripts). The behavioral rules in pipeline-orchestration.md are the primary
# constraint; this hook is the mechanical backstop.
# agent_type comes from the subagent's frontmatter name field (or the Agent
# tool's `name`, for a named teammate spawn); empty for the main thread (Eva).
exit 0
