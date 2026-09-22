# Brief: T8.6 — Brief template: add Order of work and Risks
**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh` (extra-gates: none; smoke: none; retries 1)

Notion T8.6 (L, S); source `~/OUTBOX/sdlc-playbook-gap-2026-09-15.md` gap 6. This brief is the shape's first instance, hand-written; the card's "next brief written with it" is step 5.

## Acceptance criteria
- `~/.claude/commands/plan-feature.md` step-5 fenced template carries `## Order of work` (after
  `## Files to create`) and `## Risks` (after `## Out of scope / do not touch`), text below verbatim.
- `tests/test_brief_shape.sh` exists, is green, and turns red on a fixture brief lacking either
  section or leaving one empty; `bin/verify.sh` picks it up (`tests/*.sh`) with no new skip line.
- The first `/plan-feature` run after landing produces a brief with both sections filled.

Template text (inside the ``` block, this indentation):
```
## Order of work
- numbered; the sequence /implement follows in one session — test, then the change it fails
  without, next pair; the gate run is the last step. Steps another actor runs after merge
  (deploy, sudo, unit restart) do NOT go here: they keep their own `## Land-time steps` /
  `## Runtime actions` section, which the land step reads by name.

## Risks
- what can go wrong that the gate cannot catch, one per bullet: the failure, its tell (how you
  would notice), the response (stop / revert / who decides). Not: restated out-of-scope, generic
  "tests may fail", anything a listed test already asserts. `- none: <why>` is a valid entry;
  an empty section is not.
```

## Files to modify
- `~/.claude/commands/plan-feature.md` — insert the two blocks; nothing else moves. **User scope, under
  no git repo** (`git rev-parse` fails; no `~/.claude/.git`): its history is this brief (text verbatim)
  plus the test below, and the commit body quotes the diff. The five contract files share one write
  second (2026-07-23 09:55:45), so a Mac-side source copy probably exists — update it too if found.

## Files to create
- `tests/test_brief_shape.sh` — new file (no `SHIP_RAILS_OVERRIDE`; runs on CI, no box
  precondition, no `ci-expected-skips.txt` edit). `BRIEF_SHAPE_SINCE=2026-09-23`: every
  `.claude/briefs/{,archive/}*.md` whose `**Date:**` ≥ that has both headings, each followed by ≥1
  non-blank line before the next `## `. Anchor: this brief by glob in both places. Files without
  `**Date:**` are not template briefs and are not judged. Shape of `tests/test_pointer_skills.sh`:
  `assert()` helper, one offender per line, `yes | grep -q y` canary.

## Order of work
1. `tests/test_brief_shape.sh`: checker + tmp fixtures — filled (ok), missing `## Risks` (FAIL), empty
   body (FAIL), no `**Date:**` (ignored), dated 2026-09-01 without sections (exempt). The fixture
   FAILs are the red; the live anchor is green by construction.
2. Edit the template; prove: `awk '/^```$/{f=!f} f' ~/.claude/commands/plan-feature.md | grep -c '^## Order of work$\|^## Risks$'` → 2.
3. `bash bin/verify.sh` green (no `bin/` change, so no drift line).
4. Commit by explicit path (test + this brief), Conventional Commit, body carrying the template diff.
5. First `/plan-feature` after landing: its brief carries both filled, else step 2 did not take.

## Test plan
- Automated: `tests/test_brief_shape.sh` — **recommended yes**, one reason: the file the card's gate
  names is unversioned and off-CI, so a brief-shape assertion here is the only thing that notices a
  revert (Mac re-copy, a repo override without the sections) — the `test_instruction_scaffolding.sh`
  move. Presence and non-emptiness only; it fires at `/implement`'s first gate run, one phase late.
- Manual: the awk/grep in step 2, then one `/plan-feature` on a small goal in a fresh session.

## Out of scope / do not touch
- `implement.md`, `ship.md`, `finish.md`: none parses brief sections (ship.md Gate 1 names
  acceptance/files/test plan as prose). Only `.claude/workflows/ship-dev-plan.js:86,95` reads a heading
  by name (`## Runtime actions`), which the Order of work text protects.
- `~/dev/AI_Trading_Bot/.claude/commands/plan-feature.md`: a full fork (has `## Implementation order`,
  no Risks); a repo override replaces the user file wholesale, never layers on it.
- Existing briefs (no backfill), `current.md`, `archive/`, the `shared` plugin (ships no commands —
  `skills/`, `hooks/`, `standards.md` only; cache `3badaf1d66a0` and marketplace checked).

## Risks
- Template reverted by a Mac-side re-copy of the 2026-07-23 set. Tell: the next brief lacks the
  sections → suite red at its `/implement` gate. Response: re-apply from this brief; find the source.
- Land steps folded into Order of work → ship-dev-plan's land step runs nothing on a deploy task.
  Tell: `## Runtime actions` absent from a `t.deploy` brief. Response: the section text forbids it.
- Five sibling T8.x briefs are being planned today on the old template, dated 2026-09-22 — hence the
  09-23 cutoff; a brief written with the new template on 09-22 is judged by hand (step 5) only.
- `## Risks` invites filler; the text names the exclusions and makes `- none: <why>` explicit. A shape
  red in a "SHIPS RED by design" task is a new red line and stops the land — correct; fix the brief.

## Notes / preconditions
- Confirmed 2026-09-22: no `.claude/commands/` in this repo, so `/plan-feature` loads the user-scope
  file (the skill listing's description matches it byte for byte). 14 of 16 live briefs carry `**Date:**`;
  ordering sections exist under eight ad-hoc names (`Implementation steps`, `Land-time steps`, …), a
  risk section once (`archive/2026-09-04-augustus-…`). Unverifiable here: a Mac source of the commands.
