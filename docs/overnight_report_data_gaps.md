# Overnight report data gaps — diagnosis, 2026-08-10

Written by Marcus, 2026-08-10, against `~/dev/agent-workforce` @ `35d81f2` (branch `main`).
Trigger: the overnight jobs of 2026-08-10 published three figures that disagree with each other
or with reality. This traces each to its source.

Scope note: the timers execute the **deployed** tree `~/agent-workforce/bin/`, not this source
tree. `diff -rq` of `bin/` and `profiles/` on 2026-08-10 shows only `.bak` and `__pycache__`
differences, so source and deployed are content-identical for every file named below. Any fix
still needs `bin/deploy` afterwards — nothing deploys automatically.

## Summary

| # | Gap | Kind | Owner |
|---|---|---|---|
| 1 | Inbox pending count reported as 40; real figure is 25 | wrong source | box |
| 2 | "Approval rate 8%" — real acceptance is 75% | mis-computed + mislabelled | box |
| 3 | `approvals.tsv` frozen since 2026-07-27 | upstream feed stalled | Mac |
| 4 | Every run logs `cost_usd_delta=0.000000` | false zero, not a blank | box |
| 5 | `model=unknown` on 156 of 165 cost.log rows | parser reads a dead key | box |
| 6 | "Inference served: 0% local / 100% remote" is a hardcoded literal | fabricated metric | box |
| 7 | "Error runs (7d): 2" — both from a retired path | stale but self-clearing | none |
| 8 | A `NOPROPOSAL` run has nowhere to put free-text analysis | missing channel | box, needs a call |

Gaps 4, 5 and 6 are the ones not previously reported to Dave. They are worse than the others in
kind: 1, 2 and 3 report a wrong number, while 4 and 6 report a **confident** number that was never
measured.

---

## 1. Inbox pending count — 40 vs 25

**Symptom.** 06:08 daily plan: "40 pending, 11 `bd-stall-radar` duplicates, unreviewed since
~07-20". 06:18 morning report: "25 pending review". Same metric, ten minutes apart.

**Root cause.** Three surfaces count `*.md` files on disk:

- `bin/inbox_backlog_alert.sh:30` — `find "$inbox_dir" -maxdepth 1 -type f -name '*.md' | wc -l`
- `bin/praetorium-status.sh:146` — same expression
- `profiles/daily_plan_task.md:65` — `ls -la ~/agent-worktrees/inbox/_inbox/agents/`

A proposal file is removed from that directory only by the Mac-side `agent_inbox.py promote`.
That has not run since 2026-07-27 (see gap 3). So the disk count measures *proposals ever written
and never promoted*, which is not the same set as *proposals awaiting review*: 15 of the 40 are
already dispositioned in Notion and are simply still on disk.

The secondary claim is wrong too. "Unreviewed since ~07-20" comes from the oldest file's mtime;
the oldest genuinely pending item is **BD Follow-up Drafts, 30 Jul**.

**The correct count already runs, nightly.** `bin/overnight_pre_snapshot.sh:72` calls
`agent_inbox_notion_sync.py --dry-run` and files the result as "Inbox lifecycle summary". The
morning-report profile is instructed to read that section and skip the raw count, which is the
entire reason it is right. This morning's snapshot (02:25) reported 23 pending; the 09:01
`agent-inbox-sync` run picked up the two new proposals, taking it to 25.

**Fix.** Point the three surfaces at the existing Notion-backed count. This is reuse, not new
work — two shell one-liners and one profile prompt line.

## 2. "Approval rate 8%"

**Symptom.** `_inbox/agents/_metrics/scorecard.md` reports `Approval rate | 8%` beside
`Approvals promoted / rejected / edited | 1 / 3 / 8`. Read plainly, that says 92% of agent output
is rejected.

**Root cause.** `bin/scorecard.sh:116`:

```sh
approval_rate="$(pct "$promoted" "$decisions")"   # decisions = promoted + rejected + edited
```

`decision=edited` is on the **promote** path, not the reject path.
`docs/nuc23_approval_outcomes_macside.md:31`: "`decision=edited` = the promotion modified the
proposal body before applying it (a weaker-trust signal than a clean promote)".

So of 12 recorded decisions: 1 applied as-is, 8 applied with edits, 3 discarded. Nine of twelve
were used. The displayed 8% is a **clean-promote rate wearing an approval-rate label**; real
acceptance is 9/12 = 75%.

**Fix.** Render both, and label them: `Clean-promote rate` = `promoted/decisions`, `Acceptance
rate` = `(promoted+edited)/decisions`. Changing the arithmetic alone would leave the same field
name meaning a third thing.

## 3. `approvals.tsv` frozen at 2026-07-27

`~/agent-worktrees/inbox/_inbox/agents/_metrics/approvals.tsv` holds 12 rows; the last is
`ts=2026-07-27T09:33:59+00:00 slug=2026-07-27_m1-signal-scan.md decision=edited`. No decision has
been recorded in two weeks.

The file is written only by the Mac-side `agent_inbox.py` promote/reject paths — the same pass
that removes promoted files from the inbox worktree. **One Mac-side pass therefore fixes both this
and the root cause of gap 1.** Nothing on the box can move it; the box deliberately never decides.

## 4. Every run logs a cost of exactly zero

**Symptom.** Every row in `logs/cost.log` since the 2026-07-24 migration to headless Claude Code:

```
usage_before=42.113538083 usage_after=42.113538083 cost_usd_delta=0.000000 cost_src=openrouter-key-api
```

**Root cause.** `bin/agent_propose.sh:46` `key_usage()` reads cumulative spend from the shared
OpenRouter key's `/key` endpoint, and cost is derived as `usage_after - usage_before`. The
overnight jobs no longer spend on OpenRouter — they run headless Claude Code on the subscription —
so that cumulative figure is frozen at 42.113538083 and the delta is arithmetically always 0.

This is not a missing measurement, it is a **false one**. `cost_usd_delta=0.000000` on a
498-second Opus run reads as "this was free". The scorecard's own `Cost per run` row is honest
("best-effort: unknown"), so the two disagree with each other.

Related: `tokens=unknown` is a **string literal** in the record's `printf`
(`bin/agent_propose.sh:98`) — token counts were never populated at all, on any run.

**Fix.** Minimum: when `cost_src` does not apply to the runtime that actually ran, write
`cost_usd_delta=n/a`, never `0.000000`. Better: have the Claude Code path record the cost and
token fields the CLI already emits under `--output-format json`, and set
`cost_src=claude-code`.

## 5. `model=unknown` on 156 of 165 rows

**Symptom.** `grep -oE 'model=[^ ]+' logs/cost.log | sort | uniq -c`: 156 `unknown`, 8
`anthropic/claude-haiku-4.5`, 1 `anthropic/claude-sonnet-5`. The last real value is from
2026-07-08. No run since is attributable to a model.

**Two independent causes, both live.**

*a) The parser reads a key no profile has.* `bin/agent_propose.sh:183` resolves the model with an
awk that looks for `name:` nested under `model:` in `~/.hermes/profiles/<profile>/config.yaml`.
No profile on the box uses that key:

| profile | key present |
|---|---|
| `marcus` | `default: deepseek/deepseek-v4-flash` |
| `trajan` | `default: deepseek/deepseek-v4-flash` |
| `augustus` | `default: openai/gpt-5.5` |
| `claudius` | no `model:` block at all |

It worked in early July under the `research_analyst` profile, which predates the schema change to
`default:`. The rename to `claudius` and the schema change have both landed since.

*b) The Claude Code profiles have no hermes profile directory.* Runs now log
`profile=claude-sonnet` / `claude-opus` (parsed out of `-p <name>` in `AGENT_RUNTIME_CMD`), but
`~/.hermes/profiles/claude-sonnet/` and `~/.hermes/profiles/claude-opus/` do not exist, so
resolution cannot even begin. `ls ~/.hermes/profiles/` returns only `augustus base0 claudius
default leantest marcus trajan`.

**Fix.** Accept `default:` as well as `name:`, and give the Claude Code jobs an explicit
`AGENT_MODEL` in their unit override rather than inferring it from a hermes profile that has
nothing to do with how they run.

## 6. "Inference served: 0% local / 100% remote" is hardcoded

`bin/scorecard.sh:157`:

```sh
echo "| Inference served | 0% local / 100% remote |"
```

A literal string in a table of measurements. It will report 0% local no matter what runs, which
makes it actively misleading the moment any local-tier work lands — and the local tier is already
built (`local-big`, Ollama on Arc/Vulkan).

**Fix.** Derive it from the run records, or delete the row. Deriving depends on gap 5 being fixed
first — there is currently no field that distinguishes a local run from a remote one.

## 7. "Error runs (last 7d): 2" — no action needed

Both are `profile=marcus task=overnight-morning-report outcome=FAIL`, from the retired
marcus/OpenRouter morning-report path. It failed identically every morning from 29 Jul to 5 Aug at
zero cost, was migrated to headless Claude Code, and has been green since — today's ran 69s,
`outcome=OPS`, `profile=claude-sonnet`. The last failure was 2026-08-05, so the 7-day counter
clears itself on 2026-08-12. Recorded here so it is not chased.

## 8. A `NOPROPOSAL` run has nowhere to put analysis

**Symptom.** The 2026-08-10 01:31 `augustus-content` run was carrying a one-off instruction to
report a review of the six scheduled LinkedIn posts "in the run report". The run correctly
declined to propose (no new content to add), and the delivery published only
`NOPROPOSAL`. `logs/deliver_content.log`, 2026-08-09T23:35:24Z:
`board: no rows changed | corpus: fetched, tip age 233.2h | run: NOPROPOSAL in 215s`. Augustus
noticed and posted the review by hand three minutes later. Second content-route delivery miss in
two days.

**Root cause.** `bin/deliver_proposal.sh:42` — on `NOPROPOSAL` the delivery emits only
`status_line()`: outcome, decline reason, duration. The proposal file is the only channel a run
has for free text, and a `NOPROPOSAL` run by definition does not write one.

**Fix (needs a shape decision before anyone builds it).** The mechanism already half exists:
`decline_reason()` lifts a `DECLINE:` line out of `agent_run.log` and puts it in the delivered
message. The symmetrical extension is an `ANALYSIS:` block lifted the same way. That is a small
change to an existing path, not new infrastructure — but it is a change to the delivery contract,
so it is Dave's call, not an implementer's.

---

## Fix plan

**Box-side, mechanical — no judgment calls (Trajan):** 1, 2, 4, 5, then 6 (6 depends on 5).
All five are in `~/dev/agent-workforce`, all need `bin/deploy` afterwards, and `tests/test_scorecard.sh`
already exists as the gate for 2 and 6.

**Mac-side, Dave only:** 3. One `agent_inbox.py promote` pass over the 15 dispositioned files
unfreezes the metric and removes gap 1's root cause at the same time. Worklist below.

**Awaiting a decision from Dave:** 8.

---

## Mac-side worklist for gap 3

The 40 files in `_inbox/agents/` split cleanly at 30 July: everything from 2026-07-30 onward is
genuinely pending (25 rows, Notion `Status=New`), everything before it is already dispositioned.
All 15 stale ones are `Promoted` in Notion — none rejected — so this is bookkeeping over decisions
already taken, not a review pass. Verified 2026-08-10 by joining the Notion `Filename` property
against the directory listing; every file on disk has a matching row.

`promote` archives the proposal, appends the `decision=` line to `_inbox/agents/_metrics/approvals.tsv`
and pushes the removal. It does not write canonical — that half already happened.

```bash
cd ~/dev/obsidian-ai-os-boxsafe
git fetch origin && git checkout agents/inbox && git pull

for f in 2026-07-17_dp-world-org-profile 2026-07-17_weekly-pre-assembly \
         2026-07-20_bd-stall-radar 2026-07-20_cold-chain-corridor-vs-facility-strategy \
         2026-07-20_m1-signal-scan 2026-07-22_bd-stall-radar 2026-07-23_bd-stall-radar \
         2026-07-26_bd-stall-radar 2026-07-27_bd-stall-radar 2026-07-28_bd-stall-radar \
         2026-07-28_qmd-refresh-root-cause 2026-07-28_weekly-pre-assembly \
         2026-07-29_brief-duplicate-title-gate 2026-07-29_m1-signal-scan; do
  00_system/tools/agent_inbox.py promote "$f.md"
done

00_system/tools/agent_inbox.py promote 2026-07-27_wms-implementatie-uitloop-artikel.md \
  --target website-content
```

Three things that decide the outcome:

- **`--target` is auto-detected from the proposal's own `target:` line.** Eleven of the fifteen
  carry `target: vault`. Four carry no line and default to `vault`, which is right for
  `dp-world-org-profile` (Notion `Promoted To`: `05_knowledge/dp_world_logistics_org_profile.md`)
  and `weekly-pre-assembly`. It is wrong for `wms-implementatie-uitloop-artikel`, whose
  `Promoted To` is website PR #11 — hence the separate call above, so its archive does not read as
  a vault promotion.
- **`2026-07-20_cold-chain-corridor-vs-facility-strategy` has a blank `Promoted To`** and its Notion
  title is "Blog draft: Why is cold-chain strategy moving up to corridor…". Check where that one
  actually landed before promoting it as `vault`; it is the only genuinely unclear file.
- **`--edited` is the metric.** Pass it where the body was changed before applying. `promoted` vs
  `edited` is the split the scorecard's approval rate is computed from, so a backfill that defaults
  everything to clean `promoted` inflates it in the opposite direction from gap 2's undercount.

**No action:** 7.
