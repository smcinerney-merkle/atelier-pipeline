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
# Allow git status, git diff, git log, git branch, git fetch, git show
# (read-only git operations) for everyone.
#
# G-147 (union of this fork's guard with the-guru's 6a996d3/40745cf/73107d0):
# the anchor now covers command position at start, a run of one or more of
# ; & | -- which also models bare &, |&, and ;; -- newline, or an opening
# parenthesis (so both `if true; then git commit; fi` and `(git commit)` are
# caught), and tolerates an optional then/do/else/elif shell keyword right
# before the verb. Between `git` and the verb, a run of NAMED git global
# options (GIT_GLOBAL_OPT below) is tolerated, closing the `git -C . commit`
# / `git -c user.name=x commit` bypass. The write-verb group boundary is
# ([^-[:alnum:]]|$), not \b: \b fires at a hyphen, which would also have
# blocked read-only hyphenated siblings (merge-base, merge-tree, merge-file,
# commit-graph, commit-tree, mergetool) once `merge` joined the blocked-verb
# list. The checkout branch closes every destructive form: "checkout --
# <paths>", "checkout <ref> -- <paths>", "checkout ." and any short-flag
# cluster containing f ("-f", "-fq", "-qf"). Long options (--force, --ours,
# --theirs, --patch, --detach) begin with "--" and are caught by the same
# branch. Known false positive: the "\(" anchor also fires on a parenthesis
# inside a quoted string (e.g. echo "(git add later)"). Known gap (out of
# scope, see CHANGELOG Known Issues): a shell keyword that ISN'T
# then/do/else/elif -- bare `if`, `while`, `!`, a `{ ...; }` group, `time`,
# or a leading `VAR=val` assignment -- still defeats the command-position
# anchor (`if git commit; then :; fi` leaks; so do `while git push; do :;
# done`, `! git push`, `{ git push; }`, `time git push`, `X=1 git push`).
#
# G-147-fix2 (post-blind-review, F2/F3): the option group between `git` and
# the verb used to be a GENERIC "-flag [single-non-flag-token]" repeat,
# which cut both ways in a scratch-repo replay:
#  F2 -- a write verb got swallowed as some unrelated flag's "argument" and
#     never reached the required verb-match position, e.g.
#     `git --no-pager merge --no-ff -m stash list` parsed generically as
#     --no-pager(arg=merge) --no-ff(no-arg) -m(no-arg) leaving "stash list"
#     at the match position -- so GIT_WRITE_EXEMPT's own `stash list`
#     allowlist entry fired on a command that actually ran `git merge`.
#  F3 -- conversely, a read-only subcommand's own argument got treated as a
#     bare flag's argument, and once nothing else was left to consume, that
#     leftover token collided with a blocked-verb spelling:
#     `git --no-pager grep -n commit` parsed --no-pager(no-arg), then
#     -n(arg=nothing, since a required trailing space closed that iteration
#     before "commit"), leaving bare "commit" sitting at the verb-match
#     position -- a false BLOCKED on a read-only `git grep`.
# fix2's replacement enumerated BOTH the argument-taking global options AND
# the no-argument ones by name.
#
# G-147-fix3 (post-blind-review, G1): the fix2 name-everything list was
# itself incomplete against real git 2.54.0 (Apple Git-157) -- `--no-advice`
# and `--no-lazy-fetch` are real no-argument global options this list never
# named, so each one left the write verb after it just as exposed as the
# original generic-flag bug (`git --no-advice commit -m x`, `git
# --no-lazy-fetch push` both returned rc 0). Separately, `--attr-source` is
# a real separate-argument global option this list never named either
# (`git --attr-source=HEAD commit -m x` returned rc 0), and the two
# argument-taking alternatives that WERE named only matched a single
# NON-SPACE token as the argument, so a shell-quoted argument containing a
# space split across the option boundary and the verb was never reached
# (`git -C "my dir" commit`, `git -C 'a b' push`, `git -c "a.b=c d" commit`
# all returned rc 0). `--super-prefix` was also named as argument-taking,
# but no longer exists in git 2.54 -- `git --super-prefix foo status`
# now errors "unknown option: --super-prefix" (exit 129) on this machine.
#
# Fix: stop enumerating no-argument global options by name -- a name-everything
# list is only as safe as its last audit, and `--no-advice` proved that gap
# closes silently. Instead, ANY dash-leading token that doesn't match one of
# the named argument-taking options below is treated generically as a
# no-argument flag (`-[^[:space:]]+`), so an unnamed or future no-argument
# global option can never smuggle a verb past this hook by omission the way
# `--no-advice` did. Only options that take a SEPARATE argument still need
# to be named, because only those can swallow a following token as their
# own "argument" (the F2/F3 failure mode) -- confirmed directly against real
# git 2.54 in a /tmp scratch repo: `-C`, `-c`, `--git-dir`, `--work-tree`,
# `--namespace`, `--attr-source`, and `--config-env` all consume a following
# space-separated token (verified by watching the token show up in git's own
# error text instead of being treated as the next subcommand; `E=x git
# --config-env a.b=E status` exits 0 in a scratch repo, confirming the
# separate-argument form -- not just `--config-env=a.b=E` -- is accepted by
# real git). `--exec-path` also takes a separate argument in real git,
# confirmed the same way, but is deliberately NOT named here: without a
# following `=` it prints the configured exec-path and exits WITHOUT running
# any subcommand at all (`git --exec-path status` prints a path and exits 0,
# never invoking `status`), so there is no verb position left for a write op
# to hide behind -- naming it would add a branch with nothing to close.
# `--list-cmds` was checked too and does NOT take a separate argument in real
# git at all (`git --list-cmds valX` errors "unknown option: --list-cmds" --
# the bare form is flatly rejected, only `--list-cmds=<group>` works), so it
# needs no named entry either. `--super-prefix` is dropped from the option
# group entirely, matching its removal from git 2.54 rather than a stale
# option list. Each named option's argument was, as of fix4, a double-quoted
# string, a single-quoted string, or a bare non-space token -- but each of
# those three alternatives required the QUOTE ITSELF to sit at the START of
# the argument. That check found the gap: `-c`/`-C`/`--git-dir=` (and
# siblings) accept an argument that MIXES unquoted and quoted text with no
# space between them (`user.name="Sean M"`, `my" "dir`), which is one shell
# word but does not start with a quote character, so none of the three
# fix4 alternatives matched it and the generic non-space-run alternative
# absorbed only the unquoted prefix, stopping at the embedded space and
# leaving the write verb unreached -- confirmed live: `git -c
# user.name="Sean M" commit -m x`, `git -c user.name="A B" push`, `git -c
# user.name='A B' commit`, `git -C my\ dir commit`, `git -C a"b c" commit`,
# and `git --git-dir=my" "dir commit` all returned rc 0 for colby on the
# pre-fix5 guard (the first made a real commit in a scratch repo).
#
# G-147-fix5 (post-blind-review, fourth pass, H1): replaced the
# quote-at-start alternation with GIT_SHELL_WORD, a single shared shell-word
# grammar -- a run of one or more of: a double-quoted segment, a
# single-quoted segment, a backslash-escaped character, or any other
# non-space/non-quote/non-backslash character. Because quoted segments and
# plain characters are now interchangeable REPEATED pieces of the same word
# rather than mutually exclusive whole-word alternatives, a quote appearing
# anywhere inside the token -- not just at position 0 -- is consumed as part
# of the same argument, closing the mixed quoting gap above. GIT_SHELL_WORD
# is referenced from both GIT_GLOBAL_OPT (below) and GIT_WRITE_EXEMPT
# (further down), so the fix applies identically to both regexes.
#
# Known residuals (post-blind-review, fifth pass; operator decision
# 2026-09-25: documented, not fixed): GIT_SHELL_WORD closes the mixed-quoting
# gap above but does not parse a shell word's own internal escaping or
# extend across a literal newline, so two narrower bypasses remain --
#
#  R1: an escaped quote INSIDE a quoted run. The double-quoted alternative
#      (`"[^"]*"`) stops at the first unescaped `"`, so it cannot span a
#      `\"` embedded inside the quotes; `git -c user.name="A \" B" commit`
#      returns rc 0 for colby -- the quoted-segment alternative closes at
#      `A \` and the rest is absorbed by the generic non-space-run
#      alternative, still stopping short of the verb.
#  R2: a literal NEWLINE inside a quoted option value. This hook's matching
#      is line-oriented throughout (see GIT_WRITE_EXEMPT's SINGLE-LINE-ONLY
#      property below), so a real newline inside `"[^"]*"` is invisible to
#      the regex the same way it is to `grep -q`'s per-line anchors;
#      `git -c user.name="A<LF>B" commit` (an actual newline in the command
#      string, not the two-character `\n`) returns rc 0 for colby.
#
# Both were confirmed live against this guard (`printf '%s\n' <payload> |
# env -u ATELIER_SETUP_MODE /bin/bash source/claude/hooks/enforce-git.sh`)
# and are NOT regressions -- both also return rc 0 for colby against the
# unmodified 5.2.2 guard and against the-guru's guard.
GIT_SHELL_WORD="(\"[^\"]*\"|'[^']*'|\\\\.|[^[:space:]\"'\\])+"
GIT_GLOBAL_OPT="(-C[[:space:]]+${GIT_SHELL_WORD}|-c[[:space:]]+${GIT_SHELL_WORD}|--(git-dir|work-tree|namespace|attr-source|config-env)([[:space:]]+${GIT_SHELL_WORD}|=${GIT_SHELL_WORD}|=)|-[^[:space:]]+)"
#
# GIT_WRITE_EXEMPT (operator decisions 2026-09-14, ported from the-guru's
# 40745cf). Three properties, each load-bearing, each added because its
# absence was measured as a live bypass:
#
#  1. SINGLE-LINE ONLY. 'grep -q' succeeds if ANY line matches and ^..$
#     anchors per line, so a multi-line command holding one exempt line was
#     exempted WHOLE -- measured: a write on line 1 with an exempt line 2 was
#     allowed. 'grep -z' is NOT usable to fix this here: this environment
#     resolves grep to ugrep, where -z means decompress, and BSD grep rejects
#     the flag outright. So a command containing any NEWLINE is never
#     exempt. Fails closed.
#
#  2. WHOLE-STRING match against a POSITIVE trailing-argument character
#     class, not a blocklist. A trailing token's first character must come
#     from [A-Za-z0-9_/~^@:+=] (later characters may also use '-', as of
#     G-147-fix3/G2 '.', and as of G-147-fix5/H3 '{'/'}' -- see below);
#     nothing else -- not '-' or '.' as a first character, not a quote,
#     backslash, or `$` -- is accepted anywhere in a trailing token.
#     G-147-fix2: the prior blocklist form
#     (excluding a fixed set of shell metacharacters, and only as the FIRST
#     character) missed quotes/backslashes/braces entirely, so `checkout
#     --detach "-f"`, `checkout --detach ''-f`, `checkout --detach \-f`,
#     `checkout --detach {-f,}`, and `merge --ff-only "--no-ff" feature`
#     were all wrongly exempted (measured: the first discarded uncommitted
#     changes, the second made a real merge commit).
#     G-147-fix3/G2: excluding '.' from BOTH positions correctly kept a bare
#     `.` / a leading-dot token non-exempt, but also wrongly denied
#     exemption to any ref with a dot past the first character -- measured
#     over-blocking (rc 2) on `merge --ff-only v5.2.2`, `merge --ff-only
#     origin/release-5.2.3`, and `checkout --track origin/v5.2.3`, all of
#     which match the `merge --ff-only` / `checkout --track` exempt
#     subcommands and should not have been blocked. Fix: allow '.' in the
#     CONTINUATION character class only -- the first-character class is
#     unchanged, so a bare `.` or a leading-dot token (`checkout --detach
#     .`) is still correctly NOT exempt, the same property the old
#     blocklist enforced, now enforced by the (still positive) whitelist.
#     Accepted costs: 'stash show -p' is blocked (unchanged from before);
#     and, as of G-147-fix3, a QUOTED ref (`merge --ff-only "v5.2.2"`) is
#     also not exempt -- this trailing-word class has no quote alternative,
#     unlike GIT_GLOBAL_OPT's own argument class above, so a quoted
#     exempt-subcommand argument falls through to the write-verb check
#     below and is blocked rather than exempted. Named here so it reads as
#     a deliberate, narrower scope decision rather than an oversight
#     alongside this same cycle's GIT_GLOBAL_OPT quoting fix.
#     G-147-fix5/H3: the CONTINUATION class over-blocked a reflog-style ref
#     that legitimately contains braces past the first character --
#     `stash@{1}` is a valid argument to the already-exempt `stash show`
#     subcommand, but neither `{` nor `}` was in the continuation class, so
#     `git stash show stash@{1}` returned rc 2 (wrongly BLOCKED) on the
#     pre-fix5 guard. Fix: allow '{' and '}' in the CONTINUATION character
#     class only, alongside '.' from fix3 -- the first-character class is
#     unchanged, so a token that OPENS with a brace (`{-f,}` from the fix2
#     example above) is still correctly non-exempt.
#
#  3. Sets a FLAG -- never 'exit 0'. An exit here also skipped the TEST-SUITE
#     guard further down, so one exempt line granted test-runner access too.
#     Measured. The flag scopes this to the git-write check alone.
#
#  The option-group prefix ahead of the exempt subcommand is the SAME named
#  GIT_GLOBAL_OPT list used by the write-verb match below, not a generic
#  flag-swallower -- see G-147-fix2 above for why the generic form let an
#  unrelated verb hide inside the exempt allowlist's own match (F2).
#
#  Exempt forms: merge --ff-only | stash list|show |
#                checkout --detach|--track|--help
#  NOTE: --force-with-lease was in an earlier draft of this list and is
#  REMOVED: it is a git-push option, absent from git-checkout(1). The arm
#  was dead (exempted, then rejected by git's parser) but a reader would
#  reasonably infer the push force-flag was sanctioned somewhere.
#
# Identity: ellis or a named Ellis instance (ellis-*), via _agent_matches ->
# hook_lib_agent_type_matches (see hook-lib.sh header) since agent_type
# holds the instance name for named teammate spawns.
GIT_WRITE_EXEMPT=0
if [ "$(printf '%s' "$COMMAND" | tr -cd '\n' | wc -c | tr -d '[:space:]')" = "0" ] &&
   printf '%s' "$COMMAND" | grep -qE '^[[:space:]]*git[[:space:]]+('"$GIT_GLOBAL_OPT"'[[:space:]]+)*(merge[[:space:]]+--ff-only|stash[[:space:]]+(list|show)|checkout[[:space:]]+--(detach|track|help))([[:space:]]+[A-Za-z0-9_/~^@:+=][A-Za-z0-9_/~^@:+=.{}-]*)*[[:space:]]*$'; then
  GIT_WRITE_EXEMPT=1
fi
if [ "$GIT_WRITE_EXEMPT" = "0" ] && echo "$COMMAND" | grep -qE '(^|[;&|]+|\n|\()\s*((then|do|else|elif)\s+)?git\s+('"$GIT_GLOBAL_OPT"'\s+)*((add|commit|push|reset|restore|clean|stash|revert|rm|cherry-pick|rebase|apply|am|merge)([^-[:alnum:]]|$)|checkout\s+([^[:space:]]+\s+)?(--|-[a-zA-Z]*f|\.(\s|$)))' 2>/dev/null; then
  if _agent_matches "$AGENT_TYPE" ellis; then
    exit 0
  fi
  echo "BLOCKED: Only Ellis can run git write operations (add, commit, push, reset, restore, clean, stash, revert, rm, cherry-pick, rebase, apply, am, merge, and the destructive checkout forms: checkout --, checkout -f, checkout .). Route through Ellis. Allowed for all: git status, git diff, git log, git branch, git fetch, git show, git merge --ff-only, git stash list/show, git checkout --detach/--track/--help, and non-destructive branch switching (git checkout <branch>, git checkout -b, git checkout -t)." >&2
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
