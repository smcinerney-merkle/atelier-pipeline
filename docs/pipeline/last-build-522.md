# Build Record: atelier-pipeline v5.2.2 (G-142 / G-143)

## DoR

- G-142: every guard identifies an agent by `agent_type`; for a named
  teammate `agent_type` is the NAME the spawner chose, not the definition it
  was spawned from. Two incidents: `ellis-gd-tag` (subagent_type `claude`)
  committed through the Ellis-only git guard; `agatha-disguised` would skip
  Colby's path guard and inherit Agatha's allowlist.
- G-143: four RF re-sync follow-ups -- (a) reconcile `enforce-git.sh`,
  (b) restore `ellis-*` matching in `prompt-compact-advisory.sh`,
  (c) covered by (a), (d) add the Instance Naming Convention protocol.
- Design system: None -- backend/hooks only, no UI.
- UI Contract: N/A -- backend only.

## Design as built

**New hook `enforce-spawn-name.sh`** (PreToolUse, matcher `Agent`, no `if`):
1. Unnamed spawn -> allow.
2. Named spawn, no `subagent_type` -> refuse.
3. Named spawn, name != subagent_type and doesn't start with
   `subagent_type-` -> refuse (the core G-142 rule).
4. OVERLAP: longest-matching base of `name` across
   `{subagent_type} ∪ persona-roster` (via `hook_lib_agent_base_type`) must
   equal `subagent_type`, else refuse. This is what catches
   `robert`/`robert-spec-x` and `sable`/`sable-ux-1`, which rule 3 alone lets
   through (the name does start with `subagent_type-`).
5. Fails CLOSED for named spawns when `hook-lib.sh` cannot be loaded.

Persona roster lives in one place: `hook_lib_agent_personas()` in
`hook-lib.sh` (`colby sarah agatha ellis robert robert-spec sable sable-ux
investigator poirot sherlock distillator sentinel scout synthesis eva`).
Deliberately a different list from the brain-capture allowlist in
`enforce-brain-capture-pending.sh` (excludes poirot/sherlock/etc. by design)
-- not merged.

Installed to `.claude/hooks/` only. **Cursor finding:** Cursor's
`hooks.json` (`source/cursor/hooks/hooks.json`, mirrored in
`.cursor-plugin/hooks/hooks.json`) only declares `PreToolUse` on
`Write|Edit|MultiEdit` and `SessionStart` -- there is no `Agent`-tool event
in its schema at all, so Cursor's hook system cannot see a spawn's `name` or
`subagent_type`. The gate is Claude Code only; no Cursor equivalent was
invented. Documented in the Instance Naming Convention protocol's Cursor
copy.

**`enforce-git.sh` reconciled:** kept the fork's own checkout regex (it
already blocks the 3 cases RF characterizes as LEAKS -- do not copy RF's
weaker regex); ported RF's G-111/G-112 test-runner regex (npx/pnpm
exec/yarn exec prefixes, `playwright test`,
`(npm|yarn|pnpm) (run )?test(:\S+)?`); test-execution gate now admits
`colby`, `investigator`/`poirot`, and the main thread (empty `agent_type`);
Ellis matching now goes through `hook_lib_agent_type_matches` (with an
inline `set -e`-safe fallback) instead of a hand-rolled `case`; added
`|| exit 0` on the `tool_name`/`command` jq reads. Registration `if`
removed from `.claude/settings.json`, `skills/pipeline-setup/hooks.md`,
`.cursor-plugin/skills/pipeline-setup/hooks.md`.

**`prompt-compact-advisory.sh`:** Ellis match now goes through
`hook_lib_agent_type_matches` (fallback inline if hook-lib missing) so a
named Ellis instance (`ellis-push8`) fires the wave-boundary advisory, not
just bare `ellis`.

**Instance Naming Convention (mandatory)** protocol added to
`source/shared/rules/agent-system.md`, `.claude/rules/agent-system.md`, and
`.cursor-plugin/rules/agent-system.mdc` (Cursor copy notes the
Claude-Code-only enforcement).

## Suite counts

- Baseline (all real changes applied, pre-mutation-testing):
  **1029 passed, 18 skipped, 0 failed** (99.84s).
- Final (post mutation-testing, all mutations reverted, plus
  `test_prompt_compact_advisory.py` added after baseline):
  **1033 passed, 18 skipped, 0 failed** (154.08s).
- Both runs: `env -u ATELIER_SETUP_MODE pytest tests/` against a scratch venv
  (`/tmp/colby-pytest-venv`, pytest 9.1.1 + pyyaml -- neither was present on
  the host; nothing installed inside the repo or system Python).

## Mutation table

| # | Mutation | File:line | Owning test | RED? | Restored? |
|---|----------|-----------|--------------|------|-----------|
| 1 | Rule 2 (naming) forced to `if false` | `source/claude/hooks/enforce-spawn-name.sh:101` | `test_enforce_spawn_name.py::test_refused_naming_violation` (message-specific assert) | YES (3 failed) | YES, diff clean |
| 2 | Rule 2 (naming) forced to `if true` | same:101 | `test_enforce_spawn_name.py::test_allowed_named_spawn` | YES (4 failed) | YES, diff clean |
| 3 | Rule 3 (OVERLAP) forced to `if false` | same:110 | `test_enforce_spawn_name.py::test_refused_overlap` (message-specific) | YES (2 failed) | YES, diff clean |
| 4 | Missing-type check forced to `if false` | same:77 | `test_enforce_spawn_name.py::test_refused_named_with_no_subagent_type` (message-specific) | YES (1 failed) | YES, diff clean |
| 5 | Removed `colby` from test-runner allowlist | `source/claude/hooks/enforce-git.sh:147` | `test_enforce_git_rf_parity.py::test_rf_test_runner_allowed_for_colby` | YES (25 failed) | YES, diff clean |
| 6 | Removed `investigator poirot` from allowlist | same:147 | `..._allowed_for_poirot` + `..._allowed_for_investigator` | YES (50 failed) | YES, diff clean |
| 7 | Removed `\|\| [ -z "$AGENT_TYPE" ]` main-thread admission | same:147 | `..._allowed_for_main_thread` | YES (25 failed) | YES, diff clean |
| 8 | Removed `npx\|pnpm exec\|yarn exec` invoker-prefix group | same:146 | `..._blocked_for_sarah` (npx cases) | YES (4 failed) | YES, diff clean |
| 9 | Removed optional ref-token group from checkout regex | same:102 | `test_rf_checkout_gap_inverted_to_blocked` | YES (2 failed) | YES, diff clean |
| 10 | Reverted Ellis match to exact-string `!= "ellis"` | `source/claude/hooks/prompt-compact-advisory.sh:29-33` | `test_prompt_compact_advisory.py::test_named_ellis_instance_fires_advisory` | YES (1 failed) | YES, diff clean |

All 10 mutations applied to `source/claude/hooks/*` (and mirrored to
`.claude/hooks/*` before each test run), reverted immediately after
confirming RED, then re-synced to `.claude/hooks/*` and re-verified with a
`diff` against the intended (non-mutated) content plus a scoped green
re-run. A stray `enforce-spawn-name.sh.mut` scratch file (byte-identical to
the real file, left over from an earlier `sed` attempt) was found and
deleted; no other scratch files remained. `git diff --stat` was not usable
to prove reverts for `enforce-spawn-name.sh` (new/untracked file, no
committed baseline to diff against) -- reverts for that file were instead
proven by re-diffing `source/` against `.claude/hooks/` (byte-identical)
and by the full green re-run of `test_enforce_spawn_name.py` after each
revert.

## Files changed

New:
- `source/claude/hooks/enforce-spawn-name.sh` (+ `.claude/hooks/` copy)
- `tests/hooks/test_enforce_spawn_name.py`
- `tests/hooks/test_enforce_git_rf_parity.py`
- `tests/hooks/test_prompt_compact_advisory.py`

Modified:
- `source/shared/hooks/hook-lib.sh` (+ `.claude/hooks/` and
  `.cursor-plugin/hooks/` copies) -- added `hook_lib_agent_personas`
- `source/claude/hooks/enforce-git.sh` (+ `.claude/hooks/` copy)
- `source/claude/hooks/prompt-compact-advisory.sh` (+ `.claude/hooks/` copy)
- `source/shared/rules/agent-system.md`, `.claude/rules/agent-system.md`,
  `.cursor-plugin/rules/agent-system.mdc` -- Instance Naming Convention
  protocol
- `.claude/settings.json`, `skills/pipeline-setup/hooks.md`,
  `.cursor-plugin/skills/pipeline-setup/hooks.md` -- registered
  `enforce-spawn-name.sh` in the Agent chain, removed dead `if` from
  `enforce-git.sh`, bumped hooks.md total 38 -> 39
- `tests/hooks/test_if_conditionals.py` -- T_0020_001/007/009 rewritten to
  assert the `if`'s absence instead of its presence
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json` -- version
  5.2.1 -> 5.2.2 (`.claude/.atelier-version` deliberately untouched, stays
  5.1.6, per the 91d31f8 precedent)
- `CHANGELOG.md` -- 5.2.2 entry

Pre-existing, not mine (already modified/untracked before this unit
started, per session's initial git status): `docs/pipeline/error-patterns.md`,
`docs/pipeline/pipeline-state.md`, `docs/pipeline/last-commit-521.md`. Left
untouched.

## Chose not to do

- **`skills/pipeline-uninstall/SKILL.md`'s hook file list.** It already
  enumerates a small, generic subset (`enforce-paths.sh`, not the 20+
  per-agent/brain-capture hooks that actually exist) -- stale independent of
  this unit. Adding `enforce-spawn-name.sh` to an already-incomplete
  illustrative list wouldn't fix the underlying drift and is out of this
  unit's scope (G-142/G-143). Flagging for a separate fix.
- **`docs/guide/user-guide.md` and `docs/guide/technical-reference.md`**
  reference the dead `enforce-git.sh` `if`. These are living docs Agatha
  updates at pipeline end, not Colby's territory; left untouched.
- **ADRs referencing the old `if`** (ADR-0020 etc.) -- ADR immutability;
  never updated in place.
- Did not run `scripts/release.sh` -- it also overwrites
  `.claude/.atelier-version`, which must stay at 5.1.6 per the 91d31f8
  precedent. Bumped the 4 manifest files by hand instead, matching what
  91d31f8 did.
