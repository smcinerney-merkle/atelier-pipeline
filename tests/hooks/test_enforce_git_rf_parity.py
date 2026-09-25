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
is weaker there) -- see the LEAKS-vs-BLOCKED cases below. `git switch
--discard-changes` is kept as a documented characterization gap (still
LEAKS): the regex only ever inspects the `checkout` verb, not `switch`.
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


# ── test-runner gate (G-111/G-112 ported) ────────────────────────────────

MUST_BLOCK_FOR_NON_ALLOWLISTED = [
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


@pytest.mark.parametrize("command", MUST_BLOCK_FOR_NON_ALLOWLISTED)
def test_rf_test_runner_blocked_for_sarah(hook_env, command):
    _blocked(_run(hook_env, command, "sarah"))


@pytest.mark.parametrize("command", MUST_BLOCK_FOR_NON_ALLOWLISTED)
def test_rf_test_runner_allowed_for_colby(hook_env, command):
    _allowed(_run(hook_env, command, "colby"))


@pytest.mark.parametrize("command", MUST_BLOCK_FOR_NON_ALLOWLISTED)
def test_rf_test_runner_allowed_for_poirot(hook_env, command):
    """G-143: the fork's message claimed Poirot was allowed; the code only
    admitted `colby`. This is the fix."""
    _allowed(_run(hook_env, command, "poirot"))


@pytest.mark.parametrize("command", MUST_BLOCK_FOR_NON_ALLOWLISTED)
def test_rf_test_runner_allowed_for_investigator(hook_env, command):
    """Poirot's registered subagent_type is `investigator`."""
    _allowed(_run(hook_env, command, "investigator"))


@pytest.mark.parametrize("command", MUST_BLOCK_FOR_NON_ALLOWLISTED)
def test_rf_test_runner_allowed_for_main_thread(hook_env, command):
    """G-143: pipeline-orchestration.md's mandatory gates require Eva to
    run the suite via Bash directly. The main thread has an empty
    agent_type."""
    _allowed(_run(hook_env, command, None))


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


def test_rf_switch_discard_changes_still_leaks_documented_gap(hook_env):
    """Different verb entirely (`switch`, not `checkout`); the regex never
    inspects it. Left open deliberately -- if this starts failing, the gap
    has been closed and this test should be updated on purpose, not
    treated as a surprise regression."""
    _allowed(_run(hook_env, "git switch --discard-changes main", "colby"))
