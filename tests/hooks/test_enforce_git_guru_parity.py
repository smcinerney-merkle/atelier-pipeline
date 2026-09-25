"""Parity port of the-guru's __tests__/build-integrity/hook-guards.test.ts
enforce-git.sh sections (commits 6a996d3, 40745cf, 73107d0) into this repo's
pytest hook-test style (G-147, gate union with this fork's enforce-git.sh).

Guru's suite exercises coverage this fork's own tests (test_enforce_git.py,
test_enforce_git_rf_parity.py) did not: the global-option bypass closure
(`git -C . commit`), shell-separator modeling (`;;`, bare `&`, `|&`,
then/do/else/elif prefixes), the four operator-decision verbs (stash,
revert, rm, cherry-pick, rebase, apply, am, merge), the GIT_WRITE_EXEMPT
allowlist with its single-line/whole-string/flag-not-exit properties, the
hyphenated-verb-group boundary (merge-base survives, merge blocked), and the
Ellis exemption's hyphen-anchor (ellis-state admitted, ellisfoo rejected).

G-151 (2026-09-25, operator decision, portal reconciliation) changed two of
Guru's own row groupings, ported below with the flip noted at each site:

  - P1: `merge --ff-only` is no longer exempt -- it is an ordinary
    unconditional write verb now. Guru's own `merge --ff-only origin/main`
    row moves from GURU_ALLOWED_GIT_COMMANDS into the blocked-for-colby
    group.
  - P2: a checkout positional operand (path or ref) is unconditionally
    blocked now, reversing this fork's 5.2.3 behavior of allowing a plain
    `checkout <branch>` as a non-destructive switch. Every Guru row that
    exercised that plain-branch-switch allowance (`checkout main`, and its
    compound-operator variants) moves from GURU_ALLOWED_GIT_COMMANDS into
    the blocked-for-colby group. The flag-led exemptions Guru already
    covered (`-b`, `-t`, `--detach`, `--track`, `--help`) are unaffected.
  - P4: `stash show`/`stash list` are read-only regardless of arguments now
    (no longer discriminated by trailing-argument shape). Guru's own
    `stash show .` and `stash show -p` rows move OUT of the blocked-for-
    colby group -- both are simply allowed for everyone now.

The test-suite execution guard this file used to ADAPT two of Guru's cases
against (G-114 identity, G-112 coverage gap) was DELETED entirely per
G-151/P3 -- test runners are allowed for every agent now, so there is no
guard left to adapt Guru's cases against. Those adapted tests are removed
below, not updated.
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
    "git merge --ff-only .",
    # G-151/P1: merge --ff-only is unconditional now -- this Guru row moved
    # here from GURU_ALLOWED_GIT_COMMANDS (was allowed for colby before).
    "git merge --ff-only origin/main",
    # G-151/P2: a checkout positional operand is unconditionally blocked
    # now -- these Guru rows moved here from GURU_ALLOWED_GIT_COMMANDS
    # (each was allowed for colby before, as a plain branch switch).
    "git checkout main",
    "git checkout ./src",
    "git checkout src/x.ts",
    "git checkout HEAD file.txt",
    "git checkout main src/x.ts",
    "git checkout HEAD~1 lib/f.ts",
    "git checkout -q HEAD file.txt",
    "git checkout main && echo done",
    "git checkout main; echo done",
    "git checkout main 2>/dev/null",
    "git checkout main | cat",
    "git checkout feature/foo && npm ci",
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
    "git worktree add ../x",
    "git worktree remove ../x",
    # Flag-led checkout branch forms -- the only checkout shapes still
    # exempt after G-151/P2 (see GURU_DESTRUCTIVE_GIT_WRITE_COMMANDS above
    # for every plain-positional-operand form that moved OUT of this list).
    "git checkout -b newbranch",
    "git checkout -t origin/x",
    "git checkout -b feature/x start-pt",
    "git -C . status",
    "git -C . diff --stat",
    "git --no-pager log --oneline",
    "git -C . rev-parse HEAD",
    "git stash list",
    "git stash show",
    # G-151/P4: stash show/list are read-only regardless of arguments now.
    "git stash show .",
    "git stash show -p",
    "git checkout --detach main",
    "git checkout --track origin/x",
    "git checkout --help",
    # G-151/P2: plain `git switch <branch>` stays allowed -- checkout's
    # modern replacement, deliberately not folded into the checkout
    # positional-operand block.
    "git switch main",
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


# ── DELETED (G-151/P3, 2026-09-25): test-suite guard identity (G-114) and
# coverage-gap (G-112) adaptations. The guard both sections adapted Guru's
# cases against was deleted outright -- test runners are allowed for every
# agent now, so there is no identity gate or coverage gap left to
# characterize. See tests/hooks/test_enforce_git_rf_parity.py for the
# replacement "allowed for everyone, including a previously-blocked
# identity" coverage.
