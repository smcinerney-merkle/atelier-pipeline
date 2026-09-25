"""Parity port of requirements-foundry's __tests__/hooks/enforce-git.test.ts
(178 vitest cases) into this repo's pytest hook-test style (G-143).

RF's suite exposed 46 real failures against this fork's enforce-git.sh
before the G-143 fix, split three ways:
  - 7:  npx / pnpm exec / yarn exec / `npm run test:*` / `playwright test`
        forms leaked past the test-runner regex.
  - 18: agent_type `poirot` was refused even though the block message said
        Poirot was allowed -- the code only admitted `colby`.
  - 18: the main thread (empty agent_type) was refused, though
        pipeline-orchestration.md's mandatory gates require Eva to run the
        suite via Bash directly.

The remaining 3 RF "LEAKS" characterization cases (`checkout <ref> -- <path>`,
`checkout HEAD -- .`, `checkout -fq`) are INVERTED here to BLOCKED: this
fork's own checkout regex already closes those gaps correctly (RF's regex
is weaker there) -- see the LEAKS-vs-BLOCKED cases below.

G-151/P5 (2026-09-25, operator decision): `git switch --discard-changes`
was kept as a documented, un-fixed characterization gap here through
5.2.3 (the old checkout regex never inspected `switch` at all). It is
CLOSED now -- `switch` joined the write-verb alternation and
`--discard-changes` is not one of the trailing forms GIT_WRITE_EXEMPT's
switch arm admits (see source/claude/hooks/enforce-git.sh's
GIT_WRITE_EXEMPT header) -- so the row below flips from LEAKS to BLOCKED.

G-151/P3 (2026-09-25, operator decision): the test-runner identity guard
this file's `test-runner gate` section exercised was DELETED entirely, not
narrowed -- test runners are allowed for every agent now. The
`test_rf_test_runner_blocked_for_sarah` row this section used to assert is
removed (not skipped); the "allowed for X" rows below stay, plus new rows
covering the identities that were previously refused (sarah, ellis, cal).
"""

import pytest

from conftest import build_bash_input, run_hook, run_hook_with_project_dir

HOOK = "enforce-git.sh"


def _run(tmp_path, command, agent_type=None):
    return run_hook(HOOK, build_bash_input(command, agent_type=agent_type), tmp_path)


def _blocked(r):
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


def _allowed(r):
    assert r.returncode == 0, r.stdout


# ── git-write gate: blocked for non-Ellis, allowed for Ellis ─────────────

BLOCKED_GIT_WRITE_COMMANDS = [
    "git checkout --force",
    "git checkout --ours .",
    "git checkout --theirs x",
    "git checkout --patch",
    "git checkout -f",
    "git checkout -- .",
    "git checkout --",
    "git add .",
    "git commit -m x",
    "git push",
    "git reset --hard",
    "git restore .",
    "git clean -fd",
]


@pytest.mark.parametrize("command", BLOCKED_GIT_WRITE_COMMANDS)
def test_rf_git_write_blocked_for_colby(hook_env, command):
    _blocked(_run(hook_env, command, "colby"))


@pytest.mark.parametrize("command", BLOCKED_GIT_WRITE_COMMANDS)
def test_rf_git_write_allowed_for_bare_ellis(hook_env, command):
    _allowed(_run(hook_env, command, "ellis"))


@pytest.mark.parametrize("command", BLOCKED_GIT_WRITE_COMMANDS)
def test_rf_git_write_allowed_for_named_ellis(hook_env, command):
    _allowed(_run(hook_env, command, "ellis-some-instance"))


def test_rf_git_write_ellis_lookalike_still_blocked(hook_env):
    _blocked(_run(hook_env, "git push", "ellisfoo"))


ALLOWED_GIT_COMMANDS = [
    "git status",
    "git log",
    "git diff",
    "git branch",
    "git show abc123 -- path/to/file.ts",
    "git diff -- path/to/file.ts",
    "git checkout -b newbranch",
    'echo "run git commit later"',
    # G-147 FLIP: these two moved here from BLOCKED_GIT_WRITE_COMMANDS above.
    # Before G-147, this fork's checkout regex had no exemption mechanism at
    # all, so any "checkout --<longform>" without a path was caught by the
    # "--" branch of the destructive-checkout clause and blocked. G-147 ports
    # Guru's GIT_WRITE_EXEMPT allowlist (merge --ff-only | stash list/show |
    # checkout --detach|--track|--help), which explicitly exempts a bare
    # `checkout --detach` / `checkout --help` (no trailing arg, or a trailing
    # arg not starting with '-' or '.') as a non-destructive branch operation.
    "git checkout --detach",
    "git checkout --help",
]


@pytest.mark.parametrize("command", ALLOWED_GIT_COMMANDS)
def test_rf_git_readonly_allowed(hook_env, command):
    _allowed(_run(hook_env, command, "colby"))


OVER_MATCH_COMMANDS = [
    "git addfoo .",
    "git resetter thing",
    "git cleanup tmp",
    "git commitizen",
]


@pytest.mark.parametrize("command", OVER_MATCH_COMMANDS)
def test_rf_word_boundary_over_match_guards(hook_env, command):
    _allowed(_run(hook_env, command, "colby"))


# ── test-runner commands: allowed for everyone (G-151/P3) ────────────────
# G-151/P3 deleted the identity-gated test-runner guard this section used
# to exercise. The list name is kept (RF's own case corpus) but the guard
# it once probed is gone -- every row below is now allowed regardless of
# agent identity, with no allowlist left to leak past.

TEST_RUNNER_COMMANDS = [
    "npm run test:run",
    "npm run test:e2e",
    "npm test",
    "yarn test",
    "pnpm test",
    "cd infra && npm test",
    "npx vitest run",
    "npx vitest run lib/foo.test.ts",
    "npx jest",
    "npx playwright test",
    "pnpm exec vitest",
    "vitest run",
    "jest",
    "pytest",
    "bats",
    "mocha",
    "rspec",
    "phpunit",
    "node --test",
    "go test",
    "cargo test",
    "make test",
    "dotnet test",
    "gradle test",
    "mvn test",
]


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_rf_test_runner_allowed_for_colby(hook_env, command):
    _allowed(_run(hook_env, command, "colby"))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_rf_test_runner_allowed_for_poirot(hook_env, command):
    _allowed(_run(hook_env, command, "poirot"))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_rf_test_runner_allowed_for_investigator(hook_env, command):
    """Poirot's registered subagent_type is `investigator`."""
    _allowed(_run(hook_env, command, "investigator"))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_rf_test_runner_allowed_for_main_thread(hook_env, command):
    _allowed(_run(hook_env, command, None))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_g151_p3_test_runner_allowed_for_sarah(hook_env, command):
    """G-151/P3: previously blocked identity under the deleted guard --
    allowed now that the guard is gone."""
    _allowed(_run(hook_env, command, "sarah"))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_g151_p3_test_runner_allowed_for_ellis(hook_env, command):
    """G-151/P3: previously blocked identity under the deleted guard --
    allowed now that the guard is gone."""
    _allowed(_run(hook_env, command, "ellis"))


@pytest.mark.parametrize("command", TEST_RUNNER_COMMANDS)
def test_g151_p3_test_runner_allowed_for_cal(hook_env, command):
    """G-151/P3: previously blocked identity under the deleted guard
    (see the deleted test_pytest_execution_cal_blocked in
    test_enforce_git.py) -- allowed now that the guard is gone."""
    _allowed(_run(hook_env, command, "cal-111"))


MUST_ALLOW_NON_TEST_COMMANDS = [
    "npx tsc --noEmit",
    "npm run lint",
    "npm run build",
    "npm run dev",
    "npm run db:migrate",
    "npm run db:studio",
    "npm install",
    "npm ci",
    "npx cdk diff",
    "npx cdk deploy",
    "npx prisma generate",
    "git status",
    'echo "run pytest to verify"',
    'echo "npm test"',
]


@pytest.mark.parametrize("command", MUST_ALLOW_NON_TEST_COMMANDS)
def test_rf_non_test_commands_allowed_for_non_allowlisted(hook_env, command):
    _allowed(_run(hook_env, command, "sarah"))


# ── escape hatch: docs/pipeline/.setup-mode sentinel ─────────────────────


def test_rf_setup_mode_sentinel_blocks_without_sentinel(hook_env):
    _blocked(_run(hook_env, "git push", "colby"))


def test_rf_setup_mode_sentinel_allows_with_sentinel(tmp_path):
    (tmp_path / "docs" / "pipeline").mkdir(parents=True)
    (tmp_path / "docs" / "pipeline" / ".setup-mode").write_text("")
    r = run_hook_with_project_dir(HOOK, build_bash_input("git push", agent_type="colby"), tmp_path)
    _allowed(r)


# ── checkout-gap cases: fork BLOCKS where RF characterized LEAKS ─────────
#
# RF's own test suite marks these three as LEAKS (allowed) against ITS
# hook. This fork's checkout regex already covers all three correctly --
# do not copy RF's weaker regex. Inverted here to BLOCKED per Sean's
# decision (G-143).


INVERTED_TO_BLOCKED = [
    "git checkout main -- file.ts",       # tree-ish pathspec discard
    "git checkout HEAD -- .",             # tree-ish pathspec discard, whole tree
    "git checkout -fq",                   # combined short flags
]


@pytest.mark.parametrize("command", INVERTED_TO_BLOCKED)
def test_rf_checkout_gap_inverted_to_blocked(hook_env, command):
    _blocked(_run(hook_env, command, "colby"))


def test_g151_p5_switch_discard_changes_now_blocked(hook_env):
    """G-151/P5 (closes G-145): `switch` now joins the write-verb
    alternation, and `--discard-changes` is not one of the trailing forms
    GIT_WRITE_EXEMPT's switch arm admits (same class as `-f`/`--force`).
    This flips from the documented, un-fixed LEAKS characterization this
    test used to assert (test_rf_switch_discard_changes_still_leaks_
    documented_gap) to BLOCKED."""
    _blocked(_run(hook_env, "git switch --discard-changes main", "colby"))


def test_g151_p2_plain_switch_stays_allowed(hook_env):
    """G-151/P2: unlike checkout, a plain `git switch <branch>` stays
    allowed -- switch's own exempt arm in GIT_WRITE_EXEMPT requires no
    leading flag at all."""
    _allowed(_run(hook_env, "git switch main", "colby"))
