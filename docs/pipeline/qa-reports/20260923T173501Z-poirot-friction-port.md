## DoR: Diff Metadata

**Scope:** Blind review of uncommitted working tree in
`/Users/smcine01/dev/atelier-pipeline-fork` against HEAD `831d55a`, cross-checked
against friction commits `3d760f5 3dacbdc 89c7093 6c45f83 211d5eb`
(`~/dev/friction`).

**Files changed:** 41 (`git diff 831d55a --stat`: 1246 insertions / 84
deletions) + 1 new untracked file (`tests/hooks/test_friction_hook_port.py`,
589 lines).

**Touched:** 6 agent frontmatter pairs (`.claude/agents/*.md` +
`source/claude/agents/*.frontmatter.yml`) for agatha, colby, ellis,
robert-spec, sable-ux, sarah; 11 hook scripts mirrored across `.claude/`,
`source/claude/`, `source/shared/`, `.cursor-plugin/`; `.claude/settings.json`;
two `hooks.md` skill docs; `tests/conftest.py`; `tests/hooks/conftest.py`;
`docs/pipeline/error-patterns.md`.

**New functions:** `hook_lib_agent_type_matches`, `hook_lib_agent_base_type`
(both in `hook-lib.sh` / mirrors).

**New dependencies:** none.

## Exercised

- `hook_lib_agent_base_type` invoked directly with 17 concrete inputs
  (exact match, named-instance hyphen prefix, prefix collisions
  `sable`/`sable-ux`, `robert`/`robert-spec`, empty agent_type, case
  sensitivity, argument-order independence). All behaved per the function's
  own header comment; longest-match resolution is correct in every collision
  case tested.
- `enforce-git.sh`'s destructive-checkout regex run through real `grep -E`
  (not Python `re`, which silently mis-parses the POSIX `[:space:]` class and
  gives false negatives — caught this mid-investigation) against 18 crafted
  commands. All destructive forms matched, all safe forms (`checkout main`,
  `checkout -b x`) did not.
- Full `tests/hooks/` suite run twice: once clean (545 passed, 18 skipped),
  once after two scratch-only mutations in `/tmp/atelier-scratch` (rsync copy
  of the repo, `.git` excluded; repo tree confirmed untouched afterward via
  `git status --short`):
  1. Removed the `run_per_agent_hook` owner auto-injection in
     `tests/hooks/conftest.py` → 14 pre-existing tests went red (listed
     below). Proves the fixture is load-bearing, not a vacuous pass.
  2. Broke `hook_lib_agent_type_matches` to `return 1` unconditionally in
     `source/shared/hooks/hook-lib.sh` (the file the test harness actually
     reads — `tests/hooks/conftest.py`'s `CLAUDE_DIR`/`SHARED_HOOKS_DIR`
     resolve to `source/claude/` and `source/shared/hooks/`, not `.claude/`;
     an initial attempt patching only `.claude/hooks/hook-lib.sh` had zero
     behavioral effect and only tripped the mirror-parity test) → 37 tests
     went red across `test_friction_hook_port.py`, `test_enforce_colby_paths.py`,
     `test_enforce_paths.py`. Proves the guard-behavior tests exercise the
     real self-gate, not just its presence.

## DoD: Verification

**Findings:** 2 | **Categories checked:** logic, security/permissions,
error handling, naming, dead code, cross-layer wiring (hook registration:
frontmatter ↔ settings.json ↔ shared lib), test-fixture validity.
**Grep verified:** all six path-guard `.claude/` files against their
`source/claude/` mirrors (byte-identical, `diff -q`, 12 pairs); `hook-lib.sh`
against `source/shared/hooks/` and `.cursor-plugin/hooks/` mirrors
(byte-identical); frontmatter `hooks:` command strings against
`.claude/settings.json` registration strings (byte-identical, confirms the
"single run, not double" comment claim); `hook_lib_agent_base_type` /
`hook_lib_agent_type_matches` usage sites across all hooks (`grep -rn`).
**Exercised:** see above.

## Findings

| # | Location | Severity | Category | Description | Suggested Fix |
|---|----------|----------|----------|-------------|---------------|
| 1 | `.claude/hooks/enforce-{colby,sarah,agatha,ux,product,ellis}-paths.sh` (e.g. `.claude/hooks/enforce-colby-paths.sh:78-88`) | FIX-REQUIRED | security/permissions | The new `pipeline_state_dir` exemption (`case "$FILE_PATH" in "$PIPELINE_STATE_DIR"/*) exit 0 ;; esac`) is unconditional on the *filename* — it exempts the entire `docs/pipeline/` tree, not just each agent's own `last-*.md` report as the comment states ("Every agent's `<output>` contract writes its report to `{pipeline_state_dir}/last-*.md`"). Grepping all six touched personas' `<output>` sections (`.claude/agents/{colby,sarah,agatha,sable-ux,robert-spec,ellis}.md`) turns up only Colby writing to `pipeline-state.md` — none of the other five document writing under `docs/pipeline/` at all. Per `.claude/rules/default-persona.md`, `pipeline-state.md`, `context-brief.md`, `error-patterns.md`, and `investigation-ledger.md` are Eva's exclusive files. As written, Colby, Sarah, Agatha, sable-ux, robert-spec, and Ellis can all now overwrite any of those Eva-exclusive files via `Write`/`Edit`/`MultiEdit`, not just their own report. This is a faithful, byte-for-byte port of friction commit `89c7093` (which carries the identical over-broad exemption for the same 4+1 agents) — not a regression introduced by this session — but it is a real widening relative to `831d55a`, where none of these six hooks had any self-gate or exemption at all (the whole feature is new in this diff), and it is broader than its own stated justification. | Scope the exemption to the filename pattern actually claimed, e.g. `case "$FILE_PATH" in "$PIPELINE_STATE_DIR"/last-*.md) exit 0 ;; esac`, or narrow the comment to admit the real scope and accept the risk explicitly. |
| 2 | `.claude/hooks/enforce-agatha-paths.sh:74-88` | NIT | dead code / drift-from-source | Fork added the `pipeline_state_dir` exemption block to Agatha's guard; friction's `89c7093` deliberately did not (Agatha's own allowlist is `docs/*`, a superset of `docs/pipeline/*`, confirmed by diffing friction's `89c7093` hunk for this file against the fork's — friction's has only the self-gate, no exemption). Harmless today since `docs/pipeline/*` ⊆ `docs/*`, but it silently diverges from upstream and would matter if Agatha's allowlist is ever narrowed to exclude `docs/pipeline/`. | Drop the redundant block for Agatha, or leave a comment noting it is deliberately redundant so a future narrowing of Agatha's allowlist doesn't quietly punch a hole back open. |

**Not findings (verified clean):**
- `.claude/` vs `source/claude/` vs `source/shared/` vs `.cursor-plugin/`
  mirrors: byte-identical across all touched hook scripts (Focus 1's mirror
  check). No divergence.
- `hook_lib_agent_base_type` longest-match, empty/odd input, prefix
  collisions, roster lookup: behaves exactly per its own header comment
  under direct exercise; the `enforce-brain-capture-pending.sh` change from
  keying the roster check on raw `AGENT_TYPE` to `BASE_TYPE` (resolved via
  `hook_lib_agent_base_type`) is a genuine, correct fix for named-instance
  roster lookups, not present in the friction commits but consistent with
  their design intent and not a regression.
- `tests/conftest.py`'s autouse `_strip_setup_mode` fixture: strips an env
  var that would otherwise cause ambient-environment leakage into hook
  tests; it does not fabricate a pass condition — confirmed by inspection,
  no owning test found that depends on `ATELIER_SETUP_MODE` being *unset*
  to reach an assertion it wouldn't otherwise reach.
- `tests/hooks/conftest.py`'s `run_per_agent_hook` owner auto-injection:
  proven load-bearing by mutation (Exercised, item 1) — removing it turns
  red: `test_enforce_colby_paths.py::test_T_0033_014_colby_blocked_from_github_workflows`,
  `test_enforce_paths.py::test_colby_blocks_github_workflows_ci`,
  `test_enforce_paths.py::test_colby_blocks_github_any_path`,
  `test_enforce_paths.py::test_colby_blocks_docs_path`,
  `test_enforce_paths.py::test_ellis_blocks_source_main_py`,
  `test_enforce_paths.py::test_ellis_blocks_arbitrary_source_file`,
  `test_enforce_paths.py::test_ellis_blocks_tests_dir`,
  `test_enforce_agatha_paths.py::test_T_0034_028_agatha_blocked_from_source_hooks`,
  `test_enforce_ellis_paths.py::test_T_0034_037_ellis_blocked_from_application_source`,
  `test_enforce_ellis_paths.py::test_T_0034_037b_ellis_blocked_from_docs`,
  `test_enforce_product_paths.py::test_T_0034_031_product_blocked_from_source`,
  `test_enforce_product_paths.py::test_T_0034_031b_product_blocked_from_docs_architecture`,
  `test_enforce_ux_paths.py::test_T_0034_034_ux_blocked_from_source`,
  `test_enforce_ux_paths.py::test_T_0034_034b_ux_blocked_from_docs_product`.
  These 14 tests predate self-gating (none of them ever set `agent_type`);
  the fixture is what keeps them meaningful after self-gating was added to
  hooks that previously had none, not what makes them meaningless.
- `enforce-git.sh` anchored destructive-checkout regex: matches every case
  claimed in friction commit `211d5eb` (`checkout -- .`, `checkout <ref> --
  <paths>`, `checkout .`, short-flag clusters containing `f`, long options),
  passes every safe case (`checkout main`, `checkout -b x`); regex is
  byte-identical to the friction source in all four mirrored copies.
- `.claude/settings.json`: valid JSON, four `PreToolUse` matcher groups
  (`Write|Edit|MultiEdit`, `Write|Edit`, `Agent`, `Bash`); each new hook's
  registration command string is byte-identical to its frontmatter
  `hooks:` command string (confirms the "single run, not double" claim in
  the frontmatter comments).

## Not fully exercised (time-boxed)

- `docs/pipeline/error-patterns.md`, `.cursor-plugin/skills/pipeline-setup/hooks.md`,
  `skills/pipeline-setup/hooks.md` diffs: UNVERIFIED — not read in this pass. The
  new test file asserts an "enforcement-config.json preserve-on-reinstall
  snippet in hooks.md," which passed in the full suite run, but I did not
  independently read the doc diffs.
- `SubagentStop`/`Agent`-matcher portion of `.claude/settings.json` beyond
  the `PreToolUse` block shown above: UNVERIFIED in detail (structure
  validated via `jq`, not diffed line-by-line against `831d55a`).
