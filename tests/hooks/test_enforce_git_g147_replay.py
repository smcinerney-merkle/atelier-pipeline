"""G-147 replay table: the 11 commands cited as gaps in the fork-vs-Guru
enforce-git.sh comparison, replayed against colby (blocked) and both a bare
and a named Ellis instance (allowed). See docs/pipeline/last-build-g147-git.md
for the full replay table run against the final guard."""

import pytest

from conftest import build_bash_input, run_hook

HOOK = "enforce-git.sh"

G147_ROWS = [
    "git -C . commit",
    "git -c user.name=x commit",
    "git stash",
    "git rebase",
    "git rm",
    "git revert",
    "git cherry-pick",
    "git apply",
    "git merge feat",
    "if true; then git commit; fi",
    "(git commit)",
]


def _run(tmp_path, command, agent_type):
    return run_hook(HOOK, build_bash_input(command, agent_type=agent_type), tmp_path)


@pytest.mark.parametrize("command", G147_ROWS)
def test_g147_row_blocked_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("command", G147_ROWS)
def test_g147_row_allowed_for_bare_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", G147_ROWS)
def test_g147_row_allowed_for_named_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis-g147")
    assert r.returncode == 0, r.stdout


# ── G-147-fix2 (post-blind-review): F1/F2/F3 reproducers ────────────────────
# All three verified live in a scratch repo before this fix: F1's first two
# rows discarded uncommitted changes / made a real merge commit under the
# pre-fix guard; F2's row also made a real merge commit. See
# docs/pipeline/last-fix-g147.md for the before/after rc table.

# F1: GIT_WRITE_EXEMPT's trailing-argument check tested only the raw first
# character for '-'. A shell-quoted or escaped dash slipped past that check
# and was wrongly exempted (rc 0) on the pre-fix guard.
F1_ROWS = [
    'git checkout --detach "-f"',
    "git checkout --detach ''-f",
    "git checkout --detach \\-f",
    "git checkout --detach {-f,}",
    'git merge --ff-only "--no-ff" feature',
]

# F2: the generic "-flag [single-non-flag-token]" option group let a write
# verb get consumed as some unrelated flag's "argument", never reaching the
# verb-match position -- so the command fell through to GIT_WRITE_EXEMPT's
# own allowlist entry (or, for the second row, off the end of the option
# group entirely) and was wrongly exempted (rc 0) on the pre-fix guard.
F2_ROWS = [
    "git --no-pager merge --no-ff -m stash list",
    "git --no-pager commit -m wip -- stash list",
]

# F3: the same generic option group let a read-only subcommand's own
# argument get treated as a bare flag's argument; once nothing else was
# left to consume, the leftover token collided with a blocked-verb
# spelling and a read-only command was wrongly BLOCKED (rc 2) on the
# pre-fix guard.
F3_ROWS = [
    "git --no-pager grep -n commit",
    "git --no-pager log --oneline --grep revert",
    "git --no-pager show --stat stash@{0}",
    "git -P diff --name-only -- apply.c",
]


@pytest.mark.parametrize("command", F1_ROWS + F2_ROWS)
def test_g147_fix2_f1_f2_row_blocked_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("command", F1_ROWS + F2_ROWS)
def test_g147_fix2_f1_f2_row_allowed_for_bare_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", F1_ROWS + F2_ROWS)
def test_g147_fix2_f1_f2_row_allowed_for_named_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis-g147")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", F3_ROWS)
def test_g147_fix2_f3_row_allowed_for_colby(hook_env, command):
    """Read-only commands -- allowed for colby too, not just Ellis."""
    r = _run(hook_env, command, "colby")
    assert r.returncode == 0, r.stdout


# ── G-147-fix3 (post-blind-review, G1/G2): fix2's named option list was
# itself incomplete against real git 2.54, and the exempt-tail whitelist
# over-blocked dotted refs. See docs/pipeline/last-fix-g147.md "Fix loop 2"
# for the before/after rc table.

# G1: `--no-advice` and `--no-lazy-fetch` are real no-argument git 2.54
# global options that fix2's named no-argument list never enumerated, so a
# write verb right after either one slipped past the guard unblocked (rc 0)
# on the pre-fix3 guard.
G1_NOARG_ROWS = [
    "git --no-advice commit -m x",
    "git --no-lazy-fetch push",
]

# G1: `--attr-source` is a real separate-argument git 2.54 global option
# fix2's named argument-taking list never enumerated, so neither the
# `=value` form nor the space-separated form was consumed as one unit and
# the verb after it slipped past the guard unblocked (rc 0) on the pre-fix3
# guard. The space-separated row is the one that actually depends on
# --attr-source being in the SEPARATE-argument named list rather than
# falling through to the generic no-argument catch-all: a single-token
# `=value` form is absorbed by the catch-all either way, but the
# space-separated form is only consumed together with its value when the
# option is named as separate-argument-taking (see the mutation table in
# docs/pipeline/last-fix-g147.md).
G1_ATTR_SOURCE_ROWS = [
    "git --attr-source=HEAD commit -m x",
    "git --attr-source HEAD commit -m x",
]

# G1: the two argument-taking options fix2 DID name (-C, -c) only consumed a
# single non-space token as their argument, so a shell-quoted argument
# containing a space split across the option boundary, leaving the verb
# unreached and the command unblocked (rc 0) on the pre-fix3 guard.
G1_QUOTED_ARG_ROWS = [
    'git -C "my dir" commit',
    "git -C 'a b' push",
    'git -c "a.b=c d" commit',
]

# G2: the exempt-tail whitelist excluded '.' in every position, which
# correctly kept a bare `.` / leading-dot ref non-exempt but also wrongly
# denied exemption to any dotted ref past the first character -- these
# match `merge --ff-only` / `checkout --track` but were wrongly BLOCKED
# (rc 2) on the pre-fix3 guard.
G2_DOTTED_REF_ROWS = [
    "git merge --ff-only v5.2.2",
    "git merge --ff-only origin/release-5.2.3",
    "git checkout --track origin/v5.2.3",
]


@pytest.mark.parametrize("command", G1_NOARG_ROWS + G1_ATTR_SOURCE_ROWS + G1_QUOTED_ARG_ROWS)
def test_g147_fix3_g1_row_blocked_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("command", G1_NOARG_ROWS + G1_ATTR_SOURCE_ROWS + G1_QUOTED_ARG_ROWS)
def test_g147_fix3_g1_row_allowed_for_bare_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", G2_DOTTED_REF_ROWS)
def test_g147_fix3_g2_row_allowed_for_colby(hook_env, command):
    """Dotted refs on an already-exempt subcommand -- allowed for colby too."""
    r = _run(hook_env, command, "colby")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", G2_DOTTED_REF_ROWS)
def test_g147_fix3_g2_row_allowed_for_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


def test_g147_fix3_bare_dot_checkout_still_blocked_for_colby(hook_env):
    """G2 boundary: bare '.' stays non-exempt -- checkout --detach . is
    still a destructive checkout form and stays BLOCKED."""
    r = _run(hook_env, "git checkout --detach .", "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


def test_g147_fix3_super_prefix_removed_is_unknown_option_on_real_git(hook_env):
    """G1: --super-prefix no longer exists in git 2.54 (confirmed via `git
    help git`); this hook no longer names it. Not a hook bypass -- real
    git itself refuses the option before any verb would run."""
    r = _run(hook_env, "git --super-prefix foo status", "colby")
    # Read-only verb (status) after a now-unnamed option -- the hook's own
    # generic no-argument catch-all consumes --super-prefix and allows the
    # read-only command through; real git separately refuses the option.
    assert r.returncode == 0, r.stdout


# ── G-147-fix4 (post-blind-review, third pass): `--config-env` takes a real
# SEPARATE argument in git 2.54 (`E=x git --config-env a.b=E status` exits 0
# in a scratch repo) but fix3's named separate-argument list never enumerated
# it, so the SPACE form left the verb unreached and the write slipped past
# the guard unblocked (rc 0) on the pre-fix4 guard. The `=` form
# (`--config-env=a.b=E`) was already caught by the generic no-argument
# catch-all regardless, since it's a single whitespace-delimited token
# either way -- only the space-separated and quoted-argument forms actually
# depend on `config-env` being in the named list. See
# docs/pipeline/last-fix-g147.md "Fix loop 3" for the before/after rc table.
G4_CONFIG_ENV_ROWS = [
    "git --config-env a.b=E commit",
    'git --config-env "a.b=E" push',
]


@pytest.mark.parametrize("command", G4_CONFIG_ENV_ROWS)
def test_g147_fix4_config_env_row_blocked_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("command", G4_CONFIG_ENV_ROWS)
def test_g147_fix4_config_env_row_allowed_for_bare_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


# ── G-147-fix5 (post-blind-review, fourth pass, H1/H3): a quote-anywhere
# shell-word grammar and a brace-tolerant exempt-tail continuation class.
# See docs/pipeline/last-fix-g147.md "Fix loop 4" for the before/after rc
# table.

# H1: fix4's named argument-taking options (-C, -c, --git-dir=, etc.) only
# treated a value as "quoted" when the quote character sat at the START of
# the argument. A shell word that MIXES unquoted and quoted text with no
# space between them (one shell word, quote not at position 0) was not
# recognized by any of fix4's three alternatives, so the generic
# non-space-run fallback absorbed only the unquoted prefix and stopped at
# the embedded space, leaving the write verb unreached and the command
# wrongly allowed on the pre-fix5 guard.
H1_ROWS = [
    'git -c user.name="Sean M" commit -m x',
    'git -c user.name="A B" push',
    "git -c user.name='A B' commit",
    "git -C my\\ dir commit",
    'git -C a"b c" commit',
    'git --git-dir=my" "dir commit',
]

# H3: the GIT_WRITE_EXEMPT trailing-argument CONTINUATION class did not
# include '{' or '}', so a legitimate reflog-style ref on an already-exempt
# subcommand (`stash show stash@{1}`) was wrongly BLOCKED on the pre-fix5
# guard.
H3_ROW = "git stash show stash@{1}"

# Read-only controls: option-group parsing changes touch these most
# directly, so they are spot-checked alongside the H1/H3 reproducers rather
# than relying solely on the broader parity suites.
H_CONTROL_ROWS = [
    'git -C "/tmp/a b" log',
    "git -c core.pager=cat log --grep merge",
]


@pytest.mark.parametrize("command", H1_ROWS)
def test_g147_fix5_h1_row_blocked_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 2, r.stdout
    assert "BLOCKED" in r.stdout


@pytest.mark.parametrize("command", H1_ROWS)
def test_g147_fix5_h1_row_allowed_for_bare_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", H1_ROWS)
def test_g147_fix5_h1_row_allowed_for_named_ellis(hook_env, command):
    r = _run(hook_env, command, "ellis-g147")
    assert r.returncode == 0, r.stdout


def test_g147_fix5_h3_row_allowed_for_colby(hook_env):
    """Reflog-style ref on an already-exempt 'stash show' -- allowed."""
    r = _run(hook_env, H3_ROW, "colby")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", H_CONTROL_ROWS)
def test_g147_fix5_readonly_control_allowed_for_colby(hook_env, command):
    r = _run(hook_env, command, "colby")
    assert r.returncode == 0, r.stdout


# ── G-147-pass4 (post-blind-review, fifth pass, R1/R2): two narrower
# residuals in GIT_SHELL_WORD, documented rather than fixed per operator
# decision 2026-09-25 (sha256 d69e79a06f9be6afe25987337f8babea93bf558fb42f9
# 8d5b6e7c5573a4f80dd). These characterize KNOWN, CURRENT leaks -- following
# the `test_g147_fix3_super_prefix_removed_is_unknown_option_on_real_git` /
# `test_rf_switch_discard_changes_still_leaks_documented_gap` precedent, they
# assert today's rc 0 on purpose. If either starts failing, the residual has
# been closed and this test should be updated deliberately, not treated as
# an unexplained regression.

# R1: an escaped quote INSIDE a quoted run. GIT_SHELL_WORD's double-quoted
# alternative (`"[^"]*"`) stops at the first unescaped `"`, so it cannot
# parse a `\"` embedded inside the quotes; the leftover is absorbed by the
# generic non-space-run alternative, which still stops short of the verb.
R1_ROWS = [
    'git -c user.name="A \\" B" commit -m x',
    'git -C "a \\" b" commit',
    "git -c $'user.name=O\\'Brien X' commit",
]

# R2: a literal NEWLINE inside a quoted option value. This hook's matching
# is line-oriented throughout (see GIT_WRITE_EXEMPT's SINGLE-LINE-ONLY
# property above), so a real newline inside `"[^"]*"` is invisible to the
# regex the same way it is to `grep -q`'s per-line anchors. Built with an
# actual "\n" in the Python string, not the two-character escape.
R2_ROWS = [
    'git -c user.name="A\nB" commit -m x',
    'git -C "a\nb" push',
    'git -c "x.y=1\n" commit',
]


@pytest.mark.parametrize("command", R1_ROWS)
def test_g147_pass4_r1_escaped_quote_in_quoted_run_leaks_documented_gap(hook_env, command):
    """R1: known, current leak -- documented, not fixed (operator decision
    2026-09-25). Should flip to rc 2 BLOCKED when GIT_SHELL_WORD is extended
    to parse an escaped quote inside its own quoted-segment alternative."""
    r = _run(hook_env, command, "colby")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("command", R2_ROWS)
def test_g147_pass4_r2_newline_in_quoted_value_leaks_documented_gap(hook_env, command):
    """R2: known, current leak -- documented, not fixed (operator decision
    2026-09-25). Should flip to rc 2 BLOCKED (or the command should be
    refused some other way) once this hook's line-oriented matching is
    replaced with something that inspects the whole payload, not per line."""
    r = _run(hook_env, command, "colby")
    assert r.returncode == 0, r.stdout
