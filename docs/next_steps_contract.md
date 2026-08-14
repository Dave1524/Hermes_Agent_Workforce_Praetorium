# Next-steps contract — every work summary ends with what Dave must do

Status: **PROPOSAL**, awaiting Dave's go. Written 2026-08-14 by Marcus at Dave's request.
Nothing in here is built.

## The problem

Agent output on this box is produced behind a write membrane: nothing reaches canonical, nothing
goes outward, and a large share of finished work terminates in a state only Dave can move —
a Mac-side promote, an outward email, a decision. The reports say what was *done*. They rarely say
what is now *his*, and almost never say it in a form he can act on without a follow-up question.

Three concrete instances from the last week, all of which cost a round trip:

- The eight Approved standing-research rows sat because "Approved" is a Mac-only state and no
  report ever said so, or gave the command.
- The `2026-07-27_wms-implementatie-uitloop-artikel` promote needed a non-default `--target`; that
  requirement surfaced only because Dave pasted a failure back.
- The 29-row approvals backlog was reported as a count for two days before anyone said which ~7
  rows were the actual decisions.

The fix is a fixed closing block on any message that summarises requested work. It is a
**reporting-format change**, not new capability — it cannot move the membrane, only make its
consequences legible at the moment the work is reported.

This matters most 17–31 August: with the laptop at home, the only thing Dave reads on the 31st is
these reports, and every accumulated owner-action has to be visible in them.

## Functional design

### Trigger — when the block is required

Required on any **Dave-facing** message that reports the outcome of work: a deliverable, a finding,
a diagnosis, a completed task, or a blocker that stops it.

Not required, and must not be added, on:

- a clarifying question, a one-line factual answer, or a progress ping ("picked up", "running");
- **sibling-facing messages** — a next-steps block addressed at a sibling contradicts the standing
  loop rules in TEAM.md (`end on a statement`, `do not close the loop verbally`) and re-triggers
  the exchange it is meant to close;
- **Aurelian's verdicts** — PASS / FAIL / INCONCLUSIVE / ERROR is a fixed format under his
  calibration pin. Appending to it changes what a verdict is.

Test to apply: *if this message is the answer to "what came of the thing I asked for", the block is
required.*

### Shape

One block, last thing in the message, nothing after it.

```
**Next steps**
1. Dave — <verb> <exact object> · <deadline or expiry> · <why it's yours>
2. Me — <what I do next without being asked>
3. Blocked — <what nobody can move, and on what>
```

Rules:

- **Owner-prefixed items only.** `Dave —`, `Me —`, `<Sibling> —`, or `Blocked —`. An item with no
  owner is the failure mode this whole contract exists to remove.
- **Dave's items come first**, ordered by deadline, soonest first.
- **Maximum five Dave items.** More than five is a backlog, not a next-steps list: put it in a
  named file or Notion view and spend one item pointing at it.

### What makes an item concrete

Each `Dave —` item carries three things, and is malformed without them:

1. **The exact object** — the command, the file path, the page id, the person's name. Not "the
   promote pass", but the loop he can paste. Not "follow up with the client", but who and about what.
2. **The deadline, or the expiry.** Either a date, or the condition that makes the item worthless
   ("expires when he leaves on the 17th"). An item with no clock cannot be prioritised against the
   others.
3. **Why it is his** — one of: `outward` (no box credential exists), `Mac-side` (write membrane),
   `decision` (judgment only he can make). This is the same membrane every time; naming it stops
   the recurring "why is this waiting on me" round trip.

### The null value is mandatory

If nothing is owed by Dave, the block is still written, in this form:

```
**Next steps** — nothing needed from you. <owner> has it; next change <when>.
```

This is the single most important line in the design. A required block with no legal empty value
makes agents invent work for the owner, which is worse than the current silence. "Nothing from you"
is also the answer Dave most needs during the holiday, and it is only trustworthy if it is a
deliberate value rather than an omission.

### Banned as items

- **"Let me know if you want me to proceed."** That is a question wearing a next-step's clothes.
  Either do the work, or write it as a decision item with the options named and a recommendation.
- **Restating what was already delivered.** The summary above it already did that.
- **Anything Dave cannot start without asking a follow-up.** If the item needs a path, a name or a
  date that is not in it, it is not a next step.
- **Vague verbs** — "review", "consider", "look at" — unless bound to a named artifact and a date.

### Worked example

```
**Next steps**
1. Dave — promote the 8 Approved standing-research rows: loop in
   docs/next_steps_contract.md §Rollout · before 17 Aug, else they sit until 31 Aug · Mac-side
2. Dave — mail Davey the catalogue + erkenning questions · before 17 Aug · outward
3. Me — chase the fleet-eval anchor repoint the moment the promote lands
4. Blocked — Claudius' subsidy brief, on item 2
```

## Technical approach

"All agents" spans **two runtimes that share no configuration**. A change applied to one silently
half-lands, which is the failure mode this box produces most often. Both are addressed below.

### Runtime A — the five Buzz agents

Prompt layering per turn is `[Base]` (harness) → `[System]` (`~/.config/buzz-agents/<name>.prompt`)
→ `[Team Instructions]` → `[Agent Memory — core]`.

- **Where the text goes:** a new `## Closing a report — next steps for Dave` section in
  `~/.config/buzz-team/TEAM.md`, immediately after `## Answering Dave`. TEAM.md is the shared layer
  all five agents receive every turn, and it is not on the deny-list — Marcus can write it. The
  per-agent `.prompt` charters are deny-listed and must not be touched for this; a rule that belongs
  to every agent belongs in the shared layer, not forked five ways.
- **It does not take effect until the units restart.** `buzz-acp-launch.sh:9` reads TEAM.md once at
  process start and exports it as `BUZZ_ACP_TEAM_INSTRUCTIONS`; buzz-acp ships no file-watching
  counterpart. So: `systemctl --user restart buzz-agent@{marcus,claudius,trajan,augustus,aurelian}`.
  All five, including Aurelian, who is exempt from the rule but not from the staleness gate.
- **Already gated, no new check needed for loading.** `verify-fleet.sh` gate 3
  (`assert_team_instructions`) compares the byte length of TEAM.md against each running process's
  env, and gate 7 (`assert_no_stale_config`) fails any agent whose TEAM.md mtime is newer than its
  unit start. An unrestarted fleet goes red on its own.
- **One new assertion is worth adding** to gate 3: that TEAM.md still *contains* the section. Length
  equality proves the process loaded the file; it does not prove a later edit did not delete the
  rule. One `grep -q` per run.

Cost: one file edit, one restart, one verify run. ~15 minutes, Marcus', no code.

### Runtime B — the 14 unattended timer jobs

These share only the persona charters; they never read TEAM.md. Each job's output format is
specified explicitly in its own `~/dev/agent-workforce/profiles/*_task.md`, so the contract has to
be added per profile. They split into two kinds, and the block belongs in different places:

- **Report jobs** — `daily_plan_task.md`, `overnight_morning_report_cc_task.md`,
  `eod_summary_task.md`, `weekly_pre_assembly_cc_task.md`, and the scorecard. Their delivered
  message *is* the report, so the block goes at the end of the delivered text. These are the three
  or four Dave actually reads, and the highest-value half of the change.
- **Proposal jobs** — `standing_research_cc_task.md`, `m1_signal_scan_cc_task.md`,
  `knowledge_digest_cc_task.md`, `raw_ingest_cc_task.md`, `bd_stall_radar_task.md`,
  `bd_followup_drafts_cc_task.md`. Their Buzz delivery is a three-line status; the substance is the
  proposal file. So the block becomes a required `## Next steps for Dave` section in each profile's
  proposal-format spec, and travels with the artifact into the inbox — where it is still there
  weeks later when the promote pass happens.

### Enforcement, and its limit

Prose in a profile decays. One structural check makes the proposal half self-enforcing at almost no
cost:

- Extend `bin/proposal_or_decline.sh` — the shared `AGENT_VERIFY_CMD` already wired into the
  proposal jobs — to require the `## Next steps for Dave` heading in a fresh proposal. A run that
  writes a headless proposal then **fails** instead of delivering. This is the same gate that closed
  the ten-day silent-failure regression in July, so it is the right seam and it is already load-
  bearing. ~5 lines.
- A `DECLINE:` run is unaffected: no proposal, no section, exit 0 as today.

The limit, stated plainly: **no check can tell a concrete item from a vague one.** The gate proves
the block exists. Whether item 1 is "promote the 8 rows, here is the loop, before the 17th,
Mac-side" or "review the inbox" is judgment, and judgment is the half of verification that has never
been mechanisable on this box. This contract narrows the gap; it does not close it.

## Costs and risks

- **Every report grows by 4–8 lines.** Fourteen consecutive nights of "nothing needed from you" over
  the holiday is repetitive — and is precisely the signal worth having. Accepted deliberately.
- **A mandatory block invites make-work.** The null value is the mitigation, and it is the first
  thing to check if the reports start growing invented owner-actions.
- **Contract change on the delivery path.** Same class as the still-open `ANALYSIS:` question from
  10 August: a format the delivery layer did not previously carry. Lower risk here, because the
  block is plain body text with no new marker, prefix or parser.

## Rollout

Ordered by value per unit of work, and by what survives 17 August:

1. **TEAM.md section + fleet restart + verify.** Marcus, ~15 min, no code, reversible by reverting
   one file. Covers all five Buzz agents, including every dispatch Marcus makes during the holiday.
2. **The four report profiles.** Trajan, mechanical. These are the messages Dave reads on the 31st,
   so this is the half that makes the fortnight legible.
3. **The six proposal profiles + the `proposal_or_decline.sh` assertion.** Trajan. Lower urgency —
   proposals are read at promote time, which is after the 31st either way.

Items 2 and 3 are a Trajan dispatch and need Dave's word. Item 1 needs one word.

## Open decisions for Dave

1. Go on the TEAM.md section as designed (Marcus, today).
2. Does Trajan get items 2 and 3 before the 17th, or after the 31st? Recommendation: item 2 before,
   item 3 after.
3. Confirm Aurelian stays exempt — his verdict format is pinned by calibration and appending to it
   changes what a verdict is.
