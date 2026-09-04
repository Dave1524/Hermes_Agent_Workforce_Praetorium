# Brief: W19 — the D5 campaign retirement left an executable chain behind, not two env files
**Date:** 2026-09-04   **Verify:** `bash bin/verify.sh` (repo root)

## The defect, stated once

On 2026-09-04 the two bounded D5 research campaigns were retired: `praetorium-content-strategy-research`
and `praetorium-faceless-content-research` fired their last declared runs (09-03 23:00, 09-04 01:30) and
their unit files were deleted from `/etc`. Verified today — neither appears in `/etc/systemd/system/` nor
in `systemctl list-unit-files`.

The retirement commit (`1bc6a4c`) touched exactly two files: `config/fleet-units.tsv` and
`design/agents/augustus.toml`. **Those are the two the repo had a check for.** `tests/test_fleet_ownership.sh`
failed in the manifest→list direction until the `.tsv` was re-materialised — the commit message says so.
Nothing failed for anything else, so nothing else was touched.

W19 was opened as "two override envs outlive their units". That was the visible tip. The retirement
actually left **a complete, reachable, deployed execution chain** plus two stale registry rows:

| # | Residue | Tree | Has a check? |
|---|---|---|---|
| 1 | `~/.config/agent-workforce/content_strategy.env` (16 lines) | deny-listed config | no — unreadable to every agent here |
| 2 | `~/.config/agent-workforce/faceless_content.env` (11 lines) | deny-listed config | no — same |
| 3 | `bin/run_content_strategy_cc.sh` | `bin` (deployed) | drift compares it; nothing calls it |
| 4 | `bin/run_faceless_content_cc.sh` | `bin` (deployed) | same |
| 5 | `bin/run_standing_research_topic_cc.sh` | `bin` (deployed) | same |
| 6 | `profiles/standing_research_content_strategy_task.md` | `profiles` (deployed) | same |
| 7 | `profiles/standing_research_faceless_content_task.md` | `profiles` (deployed) | same |
| 8 | `design/workflow-registry.md:77-78` — both rows still `keep` | `design` | **referenced by no test and no script** |
| 9 | `design/eval-spec.md:166-167` — both rows still present | `design` | file is read by two suites; these rows are not asserted |
| 10 | `design/agents/augustus.toml:33` — `[surfaces.scheduled]` `present = true`, `governed_by` = the runner at #5 | `design` | no test asserts a present surface has workflows |
| 11 | `design/agents/augustus.toml:78` — `augustus-content` notes still describe a 01:30 lock collision with `praetorium-faceless-content-research` | `design` | not asserted |

Items 10 and 11 are in the file the retirement **did** edit. It removed the two `[[workflows]]` entries and
added a comment explaining the removal, and left the surface those workflows were the only occupants of, and
a note describing a collision with a unit it had just deleted.

**The chain is closed and self-documenting.** `bin/run_content_strategy_cc.sh:2-3` says in its own header
that it is "wired as `AGENT_RUNTIME_CMD` in `~/.config/agent-workforce/content_strategy.env`". So the repo
records what the deny-listed half contains without reading it: env → shim → shared runner → task profile.
Nothing outside that chain calls any link of it — `grep` over the whole repo finds `run_standing_research_topic_cc`
named only by its own two shims and by `augustus.toml`'s `governed_by`, and its topic switch accepts exactly
`content-strategy|faceless-content` (`bin/run_standing_research_topic_cc.sh:12-23`), which are the two
retired campaigns and nothing else. With the units gone, no timer, unit or script can reach any of it.

## Why this is W17's class, and the generalisable part

W17 was a deploy destination compared by nothing. This is the same shape one level up: **the retirement was
as complete as the repo's joins forced it to be, and no more.** `config/fleet-units.tsv` was corrected
because a test failed. `design/workflow-registry.md` was not, and it is referenced by **no test and no
script** — verified by grep over `tests/` and `bin/`. Same commit, same author, same intent; the difference
was purely mechanical.

The rule worth keeping: **when a registry has no consumer, its rows are prose, and prose does not get
retired.** A registry nobody joins against is a document that will disagree with the box and never say so.

## Acceptance criteria

1. `design/workflow-registry.md:77-78` no longer present both campaigns as `keep` with live triggers.
   Follow the precedent already set in `design/agents/augustus.toml`: remove the rows and leave a dated
   note recording the retirement, rather than marking them `spent` — a `spent` entry names a unit that
   exists in no tree, which is the defect `deploy-exclusions.toml`'s header calls "an exclusion that
   outlives its subject".
2. `design/eval-spec.md:166-167` likewise; and the "four suites" backlog figure below them re-checked
   against the new denominator rather than left as-is.
3. `design/agents/augustus.toml` `[surfaces.scheduled]` reflects that it now hosts zero workflows, and
   the `augustus-content` collision note no longer describes a collision with a deleted unit.
4. Items 3-7 removed from source, with the two `profiles/` files declared in
   `design/deploy-exclusions.toml` (see the coupling below).
5. The W19 row in `design/open-decisions.md` records the widened scope and points here.
6. `bash bin/verify.sh` green, or red **only** on the drift findings item 4 deliberately opens.

## The coupling that makes this not-piecemeal — read before starting item 4

`bin/deploy` is additive. Deleting a file from source leaves the deployed copy in place until
`bin/deploy --prune` runs, and the drift check reports it. For **content** trees that is a declarable state:
`design/deploy-exclusions.toml` exists precisely for it, carries no expiry by design, and is checked in both
directions so it self-clears on the next prune. The two `profiles/` files (items 6-7) go there.

**The `bin` half has no such escape.** `bin/check_deploy_drift.sh:334` reports `runtime-only: <f> has no
source` unconditionally; only the content-tree loop consults the exclusions (`:392`). So deleting items 3-5
from source makes the gate **hard red with no declarable exemption**, and the only remedy is
`bin/deploy --prune` — which is `rsync --delete` across all eight paths, cannot be aimed, and would also
drop the nine content exclusions that are currently deferred on purpose.

Three consequences, in order of preference:

- **Do items 1-3, 5 and the `profiles/` half of 4 now.** They are `design/` and `profiles/` only; no `bin/`
  deletion, no prune, gate stays green.
- **Do the `bin/` half (items 3-5) as one deliberate act with `--prune`,** at a time Dave chooses, accepting
  that the nine deferred exclusions clear in the same run. That is not a side effect to hide in a docs PR.
- **Or leave the three `bin/` scripts.** They are inert: no unit, timer or script can reach them, and the
  runner refuses any argument that is not one of the two dead topics. Inert is not dangerous.

Whether the `bin` half *should* consult `deploy-exclusions.toml` is a real open question this brief raises
and does not answer. The asymmetry looks deliberate — the loop comment at `:355-357` presents the exclusion
lookup as an addition the content trees have — but the argument for it in that file's header ("every source
deletion opens a window") is not weaker for `bin/`. Do not change it as part of this cleanup; it is its own
decision with its own blast radius.

## The Dave-only half — items 1 and 2

`~/.config/agent-workforce/` is on the Claude Code deny-list. No agent on this box can read, write, list or
verify it, and `bin/deploy` never writes it. There is no instrument here; the only one is a human running
`ls`. This half is Dave's and must not be attempted from a session.

    ls -l ~/.config/agent-workforce/content_strategy.env ~/.config/agent-workforce/faceless_content.env
    rm ~/.config/agent-workforce/content_strategy.env ~/.config/agent-workforce/faceless_content.env

Safe to run whenever: both files are `AGENT_JOB_OVERRIDES` for units that no longer exist, and no surviving
unit names either path. **Not urgent** — a config file for a unit that cannot start is inert. Do it before
items 3-5, or the shims' headers stop being an accurate description of what is on disk.

## Test plan

No new behaviour, so no new suite. What must hold:

1. `bash bin/verify.sh` from the repo root: 0 FAIL, and `drift:` clean unless item 4's `bin` half was taken.
2. `grep -rn 'content-strategy\|faceless-content' design/ profiles/ bin/ config/` returns only historical
   notes that name a date and say "retired" — no row, manifest entry or table cell presenting either
   campaign as live.
3. `systemctl list-unit-files | grep -E 'content-strategy|faceless'` stays empty. If it ever does not, the
   units came back and this brief is void.
4. If the `profiles/` deletions land: `bin/check_deploy_drift.sh` names both as declared runtime-only
   pending prune, and `design/deploy-exclusions.toml` grows from 9 entries to 11.

## Out of scope / do not touch

- **`bin/deploy --prune`.** Not in this brief. It cannot be aimed and it clears nine deferred exclusions.
- **The `bin`-half exclusion asymmetry.** Named above as an open question; changing it is a separate brief.
- **`design/deploy-exclusions.toml`'s no-dates rule.** Do not add an expiry to any entry created here.
- **The archived campaign material** under `.claude/briefs/archive/` and the `open-decisions.md` items 7 and
  the D5 records. Those are history and are correct as history.
- **Re-enabling anything.** The campaigns were authorised for a fixed number of nights and spent them.
  Expiry is the design (`design/workflow-registry.md:100-108`), not a defect.

## Notes / preconditions

- Every claim about `/etc` and `systemctl` here was measured on 2026-09-04 in this session.
- Every claim about the two `.env` files is **second-hand**: line counts (16, 11) come from a `wc -l` Dave
  pasted for an unrelated check, and their contents are inferred from the two shims' own headers. That is
  the only route available, and it is the same route by which W19 was found at all.
- The auto-sync timer commits and pushes any dirty tree in `~/dev/agent-workforce` within 15 minutes.
  Commit promptly, and branch in a worktree — never in the canonical checkout, whose `main` the timer
  asserts.
