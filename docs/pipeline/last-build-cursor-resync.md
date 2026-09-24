# Build Report: Cursor agent resync + parity test

## DoR

- 12 of 14 `.cursor-plugin/agents/*.md` had drifted from `source/shared/agents/*.md`
  (per-agent line counts in the task matched exactly what evidence-diffing below
  reproduced).
- `scout.md` and `synthesis.md` matched their shared bodies byte-for-byte already
  -- used as the reference for the assembly rule.
- `colby.md`'s `<output>` contract had already been re-synced by an earlier,
  uncommitted session edit; verified it needed no further change under the
  derived rule (see below).
- Design system: None -- backend/template-content work only, no UI.
- No ADR/spec/UX doc for this unit; scope came directly from the task brief.

## Assembly rule (derived from evidence, not assumed)

Read `skills/pipeline-setup/SKILL.md` (Step 3 installation manifest) and
`skills/pipeline-setup/hooks.md` (brain-extractor row) -- neither describes a
Cursor-specific placeholder-resolution table for agent bodies; both simply say
"assembled from `source/shared/` + `source/cursor/` overlays."  So the rule had
to come from diffing the two already-matching files against their shared
counterparts, then confirming against the one already-fixed file (`colby.md`):

1. `diff source/shared/agents/scout.md .cursor-plugin/agents/scout.md` -> empty.
   `scout.md` contains no `{...}` placeholders at all, so this only proves "no
   frontmatter is prepended to the Cursor `.md` body" -- frontmatter for Cursor
   lives solely in `source/cursor/agents/<name>.frontmatter.yml` and is never
   concatenated into the `.md` file (unlike the Claude Code assembly, which
   still keeps `.claude/agents/*.md` as body-only too, but that side keeps every
   placeholder literal -- see point 3).
2. `synthesis.md` matched the same way (also no placeholders).
3. `colby.md` was the tie-breaker. Its `.cursor-plugin` copy (already
   hand-patched this session, at line 51 pre-existing from an earlier state)
   showed `{lint_command}` / `{typecheck_command}` resolved to
   `echo "no linter configured"` / `echo "no typecheck configured"` -- this
   project's own `CLAUDE.md` Test Commands values -- while `{test_command}`
   at lines 55/57/212 stayed **literal**, unresolved, matching the shared
   source exactly (contributing zero diff). Cross-checked `{config_dir}` /
   `{pipeline_state_dir}`: resolved to `.cursor` / `docs/pipeline` in the
   Cursor copy, left literal in `.claude/agents/colby.md`.
4. Checked the pre-fix (drifted) `.cursor-plugin/agents/sarah.md`: it had
   `{adr_dir}` and `{slug}` hard-coded to `docs/architecture` /
   `ADR-NNNN-feature-slug.md` -- stale content from before those became
   templated runtime slots in the shared body. This confirmed `{adr_dir}` and
   `{slug}` are runtime slots that must stay literal, matching the task's own
   explicit example list.

**Rule:** `.cursor-plugin/agents/<name>.md` = `source/shared/agents/<name>.md`
body, verbatim, with exactly four config-time placeholders resolved:

| Placeholder | Resolves to |
|---|---|
| `{config_dir}` | `.cursor` |
| `{pipeline_state_dir}` | `docs/pipeline` |
| `{lint_command}` | `echo "no linter configured"` |
| `{typecheck_command}` | `echo "no typecheck configured"` |

Every other placeholder (`{feature}`, `{slug}`, `{path}`, `{paths}`, `{thing}`,
`{adr_dir}`, `{test_command}`, `{Title}`) is a runtime slot and stays literal
in both files. No frontmatter is added to the Cursor `.md` body.

Verified this rule reproduces the task's stated diff counts exactly
(agatha 21, distillator 1, ellis 8, investigator 30, robert-spec 24, robert 11,
sable-ux 20, sable 12, sarah 15, sentinel 4, sherlock 7) before writing any
files, and that `colby` came out at 0 diff under the rule (its remaining
"2 lines" in the task's snapshot were already closed by the prior session's
edit to the `<output>` contract).

## What changed, per agent (regenerated .cursor-plugin/agents/<name>.md from source/shared/agents/<name>.md)

- **agatha.md** -- picked up newer shared-body sections not previously mirrored (21 lines).
- **distillator.md** -- single-line drift, resolved placeholder mismatch (1 line).
- **ellis.md** -- picked up shared-body updates not previously mirrored (8 lines).
- **investigator.md** -- picked up the "three-pass attention allocation" workflow addition and the append-only `qa-reports/` archive-write `<output>` contract from commit `831d55a` (30 lines) -- confirmed by diffing before regenerating.
- **robert-spec.md** -- picked up shared-body updates not previously mirrored (24 lines).
- **robert.md** -- picked up shared-body updates not previously mirrored (11 lines).
- **sable-ux.md** -- picked up shared-body updates not previously mirrored (20 lines).
- **sable.md** -- picked up shared-body updates not previously mirrored (12 lines).
- **sarah.md** -- replaced hard-coded, stale `docs/architecture` / `ADR-NNNN-feature-slug.md` text with the current shared body's literal `{adr_dir}`/`{slug}` runtime-slot placeholders, plus other shared-body updates (15 lines).
- **sentinel.md** -- picked up shared-body updates not previously mirrored (4 lines).
- **sherlock.md** -- picked up the append-only case-file archive `<output>` contract from commit `831d55a`, plus other updates (7 lines).
- **colby.md** -- no change (already regenerated correctly by the prior uncommitted session edit; verified 0-diff under the rule).
- **scout.md**, **synthesis.md** -- no change (already matched).

`source/shared/agents/` and `.claude/` were not touched.

## Test added

`tests/test_cursor_agent_parity.py` -- 3 fixed assertions (agents discovered,
no missing Cursor copies, no extra Cursor copies) + 14 parametrized
(`test_cursor_agent_matches_assembled_shared_body[<name>]`, one per agent in
`source/shared/agents/`). Applies the same four-placeholder resolution rule
in-test and asserts byte-for-byte equality against
`.cursor-plugin/agents/<name>.md`. Fails on drift, on a missing Cursor copy,
and on an orphan Cursor copy with no shared source.

Test name for scoped re-runs: `tests/test_cursor_agent_parity.py`.

## Mutation evidence

1. **Red against the pre-fix tree (real repo, no scratch needed for this half):**
   Restored `.cursor-plugin/agents/sarah.md` to its `8b22771` (pre-fix) content
   in place, ran `pytest ... -k sarah` -> 1 failed (drift correctly detected:
   stale `docs/architecture`/`ADR-NNNN-feature-slug.md` text vs. the current
   shared body's `{adr_dir}`/`{slug}` placeholders). Restored the regenerated
   content, re-ran -> 1 passed.
2. **Scratch-copy mutation check (per constraint):** `rsync -a --exclude .git`
   the whole tree to `/tmp/atelier-scratch/`. In the scratch copy, overwrote
   `.cursor-plugin/agents/ellis.md` with its `8b22771` content
   (`git show 8b22771:.cursor-plugin/agents/ellis.md`). Ran
   `pytest tests/test_cursor_agent_parity.py -k ellis` from inside
   `/tmp/atelier-scratch` -> 1 failed, confirming the test goes red on the
   mutation. Deleted `/tmp/atelier-scratch` afterward (`rm -rf`); confirmed
   gone.
3. Full suite re-run against the real, fixed tree: `17 passed`.

## Command used for all runs

`env -u ATELIER_SETUP_MODE uvx --with pyyaml pytest -p no:cacheprovider -q tests/test_cursor_agent_parity.py`

(and the same with `-k <name>` for the two red-check runs). No other test
files were run. `docs/pipeline/` was not touched by this unit except for this
report file.

## Lint / Typecheck

Both are no-ops per this project's `CLAUDE.md`:
`echo "no linter configured"` and `echo "no typecheck configured"` -- ran,
both exit 0.

## Fix cycle: platform-paths-only rule

The original assembly rule (four placeholders resolved) baked this fork's
own `CLAUDE.md` Test Commands values into `.cursor-plugin/agents/colby.md`.
That was wrong for what `.cursor-plugin/` actually is: the Cursor plugin
**as shipped to every installing project**, not this fork's own installed
copy the way `.claude/` is. `{lint_command}`/`{typecheck_command}` are
per-installing-project config -- resolving them at assembly time ships this
repo's own no-op echo commands to every downstream Cursor user, silently
disabling their real lint/typecheck gate regardless of their own project's
setup. `{config_dir}` and `{pipeline_state_dir}` are different in kind:
both are platform paths fixed by which IDE plugin this is (`.cursor` /
`docs/pipeline`), not by which project installs it -- safe to bake in.

**Rule now:** exactly two placeholders resolved at Cursor assembly --
`{config_dir}` -> `.cursor`, `{pipeline_state_dir}` -> `docs/pipeline`.
`{lint_command}` and `{typecheck_command}` stay literal, same as
`{test_command}` and every `.claude/agents/` copy already does.

### Test changed

`tests/test_cursor_agent_parity.py`:
- `CURSOR_PLACEHOLDER_RESOLUTIONS` dropped `{lint_command}` /
  `{typecheck_command}`, keeping only the two platform-path entries.
- Module docstring and the per-agent assertion message rewritten to state
  the platform-paths-only rule and why (`.cursor-plugin` is the distributed
  plugin; project config values must not be baked into it).
- Fixed a stale "four config-time placeholders" docstring reference on
  `test_cursor_agent_matches_assembled_shared_body` to "two."

### Regeneration verified against all 14, not assumed

Ran the new two-placeholder substitution against every
`source/shared/agents/*.md` and diffed against the current
`.cursor-plugin/agents/*.md` before editing anything. Exactly one file
differed: `colby.md` line 51, `Run: \`echo "no linter configured" &&
echo "no typecheck configured"\`.` needed to revert to `Run: \`{lint_command}
&& {typecheck_command}\`.` -- matching the expectation stated in the fix
brief. The other 13 files needed no change (their only resolved
placeholders were already `{config_dir}`/`{pipeline_state_dir}`). Re-ran
the full 14-file substitution-and-diff after the edit: 0 mismatches.

Files touched: `.cursor-plugin/agents/colby.md` (1 line) and
`tests/test_cursor_agent_parity.py`. No change to
`source/shared/agents/`, `.claude/`, or any other `.cursor-plugin/agents/`
file.

### Mutation check (scratch copy, per constraint)

`rsync -a --exclude .git` the tree to `/tmp/atelier-scratch2/`. In the
scratch copy, restored the pre-fix echo line into
`.cursor-plugin/agents/colby.md`. Ran
`env -u ATELIER_SETUP_MODE uvx --with pyyaml pytest -p no:cacheprovider -q tests/test_cursor_agent_parity.py -k colby`
from inside `/tmp/atelier-scratch2` -> 1 failed, confirming the new rule
catches the exact regression this fix cycle addresses. Deleted
`/tmp/atelier-scratch2` afterward (`rm -rf`); confirmed gone (`ls` on the
path errors "No such file or directory").

### Test run (real, fixed tree)

`env -u ATELIER_SETUP_MODE uvx --with pyyaml pytest -p no:cacheprovider -q tests/test_cursor_agent_parity.py`
-> `17 passed`. No other test files were run.
