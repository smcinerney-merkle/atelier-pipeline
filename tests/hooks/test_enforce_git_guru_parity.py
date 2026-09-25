"""Parity port of the-guru's __tests__/build-integrity/hook-guards.test.ts
enforce-git.sh sections (commits 6a996d3, 40745cf, 73107d0) into this repo's
pytest hook-test style (G-147, gate union with this fork's enforce-git.sh).

Guru's suite exercises coverage this fork's own tests (test_enforce_git.py,
test_enforce_git_rf_parity.py) did not: the global-option bypass closure
(`git -C . commit`), shell-separator modeling (`;;`, bare `&`, `|&`,
then/do/else/elif prefixes), the four operator-decision verbs (stash,
revert, rm, cherry-pick, rebase, apply, am, merge), the GIT_WRITE_EXEMPT
allowlist (merge --ff-only, stash list/show, checkout --detach/--track/
--help) with its single-line/whole-string/flag-not-exit properties, the
hyphenated-verb-group boundary (merge-base survives, merge blocked), and the
Ellis exemption's hyphen-anchor (ellis-state admitted, ellisfoo rejected).

Two cases from Guru's suite are ADAPTED here because they assert this fork's
test-suite rule differently -- Guru's own hook blocks the main thread from
running test suites; this fork's G-143 fix deliberately allows it (Eva's
mandatory gates require running the test command directly via Bash):

  1. "test-suite guard identity (G-114)" -- Guru asserts an empty agent_type
     (main thread) is BLOCKED from `npm test`. Flipped to ALLOWED here
     (test_g114_main_thread_allowed_for_test_suite_fork_rule).
  2. "test-suite guard coverage gap (G-112)" -- Guru characterizes
     `npx vitest run` as UNGATED for a non-allowlisted agent. This fork's
     G-143 fix already closed that specific gap (the npx-prefix group now
     covers bare-runner-name forms), so a non-allowlisted agent ("sarah") is
     now BLOCKED, not ungated. `npm run ci:test` is NOT covered by G-143 (the
     script name doesn't start with "test") and remains a genuine open gap
     in this fork too -- ported unchanged.
"""

import pytest

from conftest import build_bash_input, run_hook

HOOK = "enforce-git.sh"


def _run(tmp_path, command, agent_type=None):
    return run_hook(HOOK, build_bash_input(command, agent_type=agent_type), tmp_path)


def _blocked(r):
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


def _allowed(r):
    assert r.returncode == 0, r.stdout


# ── git-write gate: global-option bypass, shell separators, new verbs ────

GURU_DESTRUCTIVE_GIT_WRITE_COMMANDS = [
    # Global-option total-bypass closure (40745cf)
    "git -C . commit -m x",
    "git -C . push",
    "git -C . reset --hard",
    "git -C . checkout -- .",
    "git -C . stash push",
    "git --no-pager commit -m x",
    "git -c user.name=x commit -m x",
    "git --git-dir=.git --work-tree=. checkout -- .",
    "git --config-env=user.name=HOME commit",
    # Shell-separator modeling (40745cf)
    "git status & git commit -m x",
    "true & git reset --hard",
    "git log |& git commit -m x",
    "if true; then git commit -m x; fi",
    "for f in a; do git push; done",
    # Operator-decision verbs: merge, apply, am, stash, checkout long-forms
    "git merge other-branch",
    "git merge --no-ff other",
    "git merge --squash other",
    "git merge",
    "git apply p.diff",
    "git am p.mbox",
    "git stash push",
    "git checkout --force",
    "git checkout --ours f",
    "git checkout --theirs f",
    "git checkout --patch",
    "git checkout --force-with-lease",
    # Trailing-argument guard on an otherwise-exempt long-form prefix
    "git checkout --detach -f",
    "git checkout --detach --force",
    "git checkout --detach -f -q",
    "git checkout --track -f",
    "git -C . checkout --detach -f",
    "git checkout --detach .",
    "git checkout --track .",
    "git checkout --detach HEAD .",
    "git checkout --detach ./src",
    "git checkout --detach ..",
    "git stash show .",
    "git merge --ff-only .",
    "git stash show -p",
    # Pre-existing regression guards (already blocked before 40745cf)
    "git checkout -- foo.sh",
    "git checkout -- .",
    "git checkout -- src/x.ts",
    "git checkout --",
    "git checkout HEAD -- .",
    "git checkout .",
    "git checkout -f",
    "git checkout -qf main",
    "git stash",
    "git stash pop",
    "git revert HEAD",
    "git rm foo",
    "git cherry-pick abc123",
    "git rebase main",
    "git commit -m x",
    "git reset --hard",
    "git add .",
    "git push",
    "git restore foo",
    "git clean -fd",
]


@pytest.mark.parametrize("command", GURU_DESTRUCTIVE_GIT_WRITE_COMMANDS)
def test_guru_git_write_blocked_for_colby(hook_env, command):
    _blocked(_run(hook_env, command, "colby"))


@pytest.mark.parametrize("command", GURU_DESTRUCTIVE_GIT_WRITE_COMMANDS)
def test_guru_git_write_allowed_for_bare_ellis(hook_env, command):
    _allowed(_run(hook_env, command, "ellis"))


@pytest.mark.parametrize("command", GURU_DESTRUCTIVE_GIT_WRITE_COMMANDS)
def test_guru_git_write_allowed_for_named_ellis(hook_env, command):
    _allowed(_run(hook_env, command, "ellis-some-instance"))


# ── git-write gate: allowed for everyone, including the exempt forms ─────

GURU_ALLOWED_GIT_COMMANDS = [
    "git status",
    "git diff",
    "git log",
    "git branch",
    "git show HEAD:x",
    "git rev-parse HEAD",
    "git fetch",
    "git merge --ff-only origin/main",
    "git worktree add ../x",
    "git worktree remove ../x",
    "git checkout main",
    "git checkout -b newbranch",
    "git checkout -t origin/x",
    "git checkout -b feature/x start-pt",
    "git checkout ./src",
    "git checkout src/x.ts",
    "git checkout HEAD file.txt",
    "git checkout main src/x.ts",
    "git checkout HEAD~1 lib/f.ts",
    "git -C . status",
    "git -C . diff --stat",
    "git --no-pager log --oneline",
    "git -C . rev-parse HEAD",
    "git stash list",
    "git stash show",
    "git checkout --detach main",
    "git checkout --track origin/x",
    "git checkout --help",
    "git checkout -q HEAD file.txt",
    # Hyphenated-verb-group boundary: the group boundary is ([^-[:alnum:]]|$),
    # not \b, so these read-only siblings of newly-blocked `merge`/pre-existing
    # `commit`/`checkout` must NOT be caught.
    "git merge-base --is-ancestor a b",
    "git merge-tree a b",
    "git merge-file a b c",
    "git commit-graph verify",
    "git commit-tree x",
    "git mergetool",
    "git commit中",
    # Compound branch-switch regression guard
    "git checkout main && echo done",
    "git checkout main; echo done",
    "git checkout main 2>/dev/null",
    "git checkout main | cat",
    "git checkout feature/foo && npm ci",
]


@pytest.mark.parametrize("command", GURU_ALLOWED_GIT_COMMANDS)
def test_guru_git_readonly_allowed_for_colby(hook_env, command):
    _allowed(_run(hook_env, command, "colby"))


@pytest.mark.parametrize("command", GURU_ALLOWED_GIT_COMMANDS)
def test_guru_git_readonly_allowed_for_ellis(hook_env, command):
    _allowed(_run(hook_env, command, "ellis"))


# ── Ellis exemption hyphen anchor ─────────────────────────────────────────


def test_guru_ellis_hyphen_anchor_allows_bare_ellis(hook_env):
    _allowed(_run(hook_env, "git reset --hard", "ellis"))


def test_guru_ellis_hyphen_anchor_allows_named_instance(hook_env):
    _allowed(_run(hook_env, "git reset --hard", "ellis-state"))


def test_guru_ellis_hyphen_anchor_blocks_lookalike(hook_env):
    """`ellisfoo` shares a prefix with `ellis` but is not a real Ellis
    instance -- the exemption must not admit it."""
    _blocked(_run(hook_env, "git reset --hard", "ellisfoo"))


# ── ADAPTED: test-suite guard identity (G-114) ────────────────────────────
# Guru's own hook blocks the main thread from `npm test`. This fork's G-143
# fix deliberately allows the main thread (Eva) -- adapted expectation below.


def test_g114_main_thread_allowed_for_test_suite_fork_rule(hook_env):
    """ADAPTED from Guru: main thread (empty agent_type) is ALLOWED to run
    the test suite under this fork's rule, not blocked."""
    _allowed(_run(hook_env, "npm test", None))


def test_g114_colby_allowed_for_test_suite(hook_env):
    _allowed(_run(hook_env, "npm test", "colby"))


def test_g114_named_colby_allowed_for_test_suite(hook_env):
    _allowed(_run(hook_env, "npm test", "colby-hook-tests"))


def test_g114_poirot_allowed_for_test_suite(hook_env):
    _allowed(_run(hook_env, "npm test", "poirot"))


def test_g114_named_poirot_allowed_for_test_suite(hook_env):
    _allowed(_run(hook_env, "npm test", "poirot-review"))


def test_g114_sarah_blocked_for_test_suite(hook_env):
    """Not in Guru's suite (Guru never allowlists anyone but Poirot/Colby to
    compare against) -- added so the identity gate has a genuine negative
    case under the fork's own allowlist (colby, investigator, poirot, plus
    the main thread)."""
    _blocked(_run(hook_env, "npm test", "sarah"))


# ── ADAPTED: test-suite guard coverage gap (G-112) ────────────────────────


def test_g112_npx_vitest_run_blocked_for_non_allowlisted_agent(hook_env):
    """ADAPTED from Guru: Guru characterizes `npx vitest run` as UNGATED for
    a non-allowlisted agent. This fork's G-143 fix already added the
    `(npx|pnpm exec|yarn exec)` prefix group ahead of the bare-runner-name
    alternatives, so this specific form is now BLOCKED for a non-allowlisted
    agent -- verified empirically before writing this test."""
    _blocked(_run(hook_env, "npx vitest run", "sarah"))


def test_g112_npx_vitest_run_allowed_for_main_thread(hook_env):
    """Main thread stays allowed regardless -- same rule as G-114, unrelated
    to whether the command shape is gated."""
    _allowed(_run(hook_env, "npx vitest run", None))


def test_g112_npm_run_ci_test_still_ungated_known_gap(hook_env):
    """NOT adapted: `npm run ci:test` is still a genuine open gap in this
    fork too. The G-143 fix's `test(:\\S+)?\\b` branch requires the script
    name to START with "test" ("test:run", "test:e2e"); "ci:test" does not,
    so this command is UNGATED for every agent including a non-allowlisted
    one. Pinned here as a known, deliberately-left-open gap per Guru's own
    docstring for this case -- not a policy endorsement, and not something
    this change fixes."""
    _allowed(_run(hook_env, "npm run ci:test", "sarah"))
