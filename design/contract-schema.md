# Workflow contract schema (D2)

**Status: DRAFT 2026-09-01.** Companion to `design/agent-model.md`. The manifest says
*what an agent may do*; a contract says *what one workflow promises*. One file per
workflow under `design/contracts/`, named for the systemd unit.

D1 deliberately kept contracts out of the registry. This is the schema they use, and
`design/contracts/knowledge-digest.md` is the worked example that proves it.

## Why contracts exist here specifically

The failures this box actually produces are almost never "the job crashed". They are:

- a job that ran, exited 0, and produced nothing (the global propose lock —
  `agent-model.md` §6.6);
- a job whose output was correct about the wrong window (bounded-window reporting bugs);
- a job that stopped being scheduled and was never missed (`agent-model.md` §6.5);
- a job that answered from a stale input while every status signal stayed green.

None of those is caught by an exit code, and none is caught by the verify gate, which
checks the *scripts* and not the *runs*. A contract is the artifact that makes them
checkable: it states what a good run leaves behind, so a bad run is a fact rather than
an absence someone has to notice.

**Contracts are therefore written to be executable by D3**, not to be read as prose. Every
`## Acceptance checks` line must be something a shell command can decide.

## Schema

A contract is markdown with these sections, in this order. All are required; a section
with nothing in it says "none" rather than being omitted.

### `## Identity`
Unit name, owner persona, surface, contract version, and the manifest it is claimed by.
The owner here must match `design/agents/<owner>.toml` — that is the one duplication in
this design, and D3's validator exists to keep the two ends equal.

### `## Trigger`
The **declared** `OnCalendar` plus `RandomizedDelaySec`, never the next-elapse time.
Registry §2 recorded next-elapse values and consequently reported three twice-weekly and
weekday-only jobs as "daily" — see `agent-model.md` §6.8. If the trigger is a finite list
of absolute dates, say so and give the expiry date.

### `## Inputs`
Every source the run reads, each with:
- **path or endpoint** — concrete;
- **freshness requirement** — how current it must be for the output to mean anything;
- **what happens when it is stale or absent** — refuse, decline, or proceed-and-flag.

The third column is the one that matters. A source with no stated staleness behaviour is
how a frozen mirror becomes a confident answer.

### `## Outputs`
The artifact: exact path pattern, format, and any hard size or shape limit. If the run
delivers, name the route and the event kind from `bin/buzz_routes.env` — a kind mismatch
is receipted `ok` and shown to nobody.

#### Outputs fields

Five bullets, each a bold label at the head of its own bullet in this section. The paragraph
above describes the mechanism — path, format, route, kind. These describe who it is for, which
the gate did not ask for until 2026-09-10 and consequently never had.

- **Beneficiary** — the person or system the artifact exists for, named. "The team" is not a
  beneficiary; `none` is an answer, and an alarming one.
- **Next actor** — who acts on it next. `none` where the artifact terminates rather than
  feeding something else, which is a different claim from having no beneficiary.
- **Next action** — the concrete thing that actor does with it. A beneficiary with no next
  action is an audience, not a consumer.
- **Benefit hypothesis** — what changes for the beneficiary when this runs, stated so it could
  turn out false.
- **Benefit signal** — what would show that it did. `Unknown` is the correct value wherever
  nothing measures it, and is preferred to a figure nobody derived: an invented number here is
  metric theatre, and the gap is the finding.

A valid empty output belongs to `## Decline conditions`, not here. Those states are enumerated
and validated there, and a second copy in this section would be a second owner of one fact —
the shape this schema keeps deleting.

### `## Decline conditions`
The enumerated states in which producing nothing is the **correct** result, and the exact
sentinel that says so. On this box that is a line matching `^DECLINE:`; anything else is a
failure. A workflow with no legitimate decline condition must say so explicitly, because
"declines are impossible here" is itself a claim D3 can test.

### `## Side effects`
Everything the run changes beyond its own artifact: git commits, branch pushes, Notion
writes, worktree state, lock files, run markers. Anything not listed here is out of
contract, and the runner's write boundary should make it impossible rather than merely
prohibited.

### `## Acceptance checks`
A numbered list. Each item states the assertion in prose and carries **exactly one** fenced
block that decides it:

    ```check id=<slug> when=<vantage>
    <bash>
    ```

These become D3's suite and T5.1's executor runs them verbatim. A check that cannot fail is not
a check — assert against what the system reports, never against a whitelist of things you
already expect to be fine.

- `id` is mandatory and unique in the file, `[a-z][a-z0-9-]*`. It is the stable name a receipt
  and the scorecard give a failed check, so prose elsewhere in the contract references a check
  by id and never by number: renumbering the list must not rename anything.
- `when` is optional, default `run`, and names a vantage declared below.
- The block is bash run with `set -u`, **no `-e` and no `pipefail`**. These are boolean
  conditions, and `pipefail` under an early-exiting reader already cost this gate one run in
  seven (`CLAUDE.md` § Verification) — inverted twice, it makes a true check red and a negated
  one green without reading anything. The block's status is its last command's, so the decision
  goes last.
- **Exit 0 passes, 77 is "not applicable", anything else fails.** 77 is this box's green skip
  already (`bin/verify.sh` treats 0 and 77 alike). A check that does not apply to this run —
  every artifact check on a run that declined — says so with 77 rather than exiting 0, so a
  receipt can tell "passed" from "never applied". Whatever the block prints lands in the
  receipt; a check that decides between branches prints which it took.

#### Executor environment

The executor exports these and nothing else, and a block reading anything else is reported by
name. Three are exported by the runner today at the lines cited; the rest the executor derives
per unit, and T5.1 is what makes them true.

- `UNIT` — the unit name with no suffix, from the manifest entry.
- `SYSTEMCTL` — `systemctl`, or `systemctl --user` where the entry says `scope = "user"`.
  Never hardcode one: half this fleet is `--user` and half is not.
- `JOURNALCTL` — the same, for `journalctl`.
- `RUN_DATE` — `YYYY-MM-DD`, exported once (`bin/agent_propose.sh:317`) and read, never
  recomputed, so a run spanning midnight cannot disagree with itself.
- `AGENT_RUN_STARTED_AT` — epoch seconds at the top of the run (`bin/agent_propose.sh:34`).
  It is what makes "this run's artifact" decidable rather than "an artifact".
- `AGENT_ATTEMPT_LOG` — this attempt's own output, truncated per attempt
  (`bin/agent_propose.sh:192`).
- `AGENT_INBOX_DIR` — where the run's artifact belongs, `$INBOX_WORKTREE/_inbox/agents`.
- `INBOX_WORKTREE` — the inbox worktree, `$HOME/agent-worktrees/inbox`
  (`bin/agent_propose.sh:24`).
- `VAULT` — the vault the run read, already resolved. `~/vault` is a symlink and a check that
  records the link rather than its target does not survive cutover.
- `HOME` — the box account's home.

**`logs/agent_run.log` is deliberately absent.** One stream carries every job with no run
boundary in it, so a line in it belongs to nobody; scoping the decline sentinel out of it was
T7.1 (2026-09-10), and handing the executor its path would invite that back. A check that wants
this run's output reads `$AGENT_ATTEMPT_LOG`; one that wants the unit's history reads the
journal, which journald scopes by unit.

#### Vantage

- `run` — decided from inside the run that just finished. It sees the artifact, the attempt log
  and the worktree, and cannot see a run that never happened, because nothing calls it.
- `sweep` — decided from outside on a cadence, over systemd and the journal. The only vantage
  that catches a timer that stopped firing or a run the global lock skipped. A check whose
  failure mode is "nothing ran" is `sweep`, or it is vacuous.

A contract for an always-on unit has no run to be decided from — no `RUN_DATE`, no attempt log,
no `LastTriggerUSec`. Where every declaring `[[workflows]]` entry carries `kind = "service"` the
check rules are skipped and the exemption is printed by name on every run; `kind` is joined
against the unit files on disk by `tests/test_fleet_ownership.sh`, so it is not self-assertion.

### `## Known failure modes`
Ways this workflow has actually failed or plausibly can, each with the signal that
distinguishes it. This is where box-specific traps get written down once instead of being
rediscovered: silent lock skips, stale-input-but-green-status, a bounded window that
outlived its boundary.

## Rules

1. **One contract per unit, named for the unit.** Two triggers on one workflow share one
   contract — `augustus-content` and `content-change-dispatch` are the live case.
2. **A contract describes the deployed runtime**, i.e. `~/agent-workforce/bin/...`, and
   cites the source path in this repo. Where they can differ, say which one was read.
3. **Freshness behaviour is mandatory on every input.** No exceptions.
4. **Acceptance checks assert the artifact, never the exit code.** `agent_propose.sh`
   exits 0 on a silent lock skip, and `bin/proposal_or_decline.sh` exists precisely
   because exit status was never sufficient.
5. **Cite what you read.** A claim in a contract without a path, a command, or a dated
   measurement is lore and will be wrong within a month.
6. **Every output names who it is for.** The five `#### Outputs fields` bullets are required
   in `## Outputs`. A workflow that cannot name a beneficiary and a next action is one nobody
   consumes, and that is a finding the gate should carry rather than a quarterly review.

**Validated in the gate since 2026-09-08 (T1.4)** by `tests/test_contract_schema.sh` /
`.py`. The eight sections above, each once, in order, none empty — and the validator reads
their names from the eight `### ` headings above rather than carrying its own copy, so
renaming a section here is the whole change. A section whose entire body is a sub-heading or
an unfilled fence counts as empty. A `## ` heading inside a fence is content; a fence that is
never closed is reported as the fence, not as the sections it swallowed.

**The `## Identity` rows are matched on their first cell, which must read `Owner` or
`Owners` and `Unit` or `Units`.** The `Owner(s)` / `Unit(s)` shorthand this document uses in
prose is not an accepted label; a row written that way is reported by name, with the
spellings that are accepted. The Owner row names each owner as a bold token (`**claudius**`)
and that set must equal the manifests whose `[[workflows]].contract` names the file, both
directions. The Unit row names the units (`buzz-agent@{marcus,trajan}.service` brace form for
a shared contract) and must equal the declaring entries' `unit` values; an escaped `\|` and a
pipe inside a code span are content rather than cell delimiters, and a systemd specifier such
as `agent-alert@%n.service` names no unit. No unit may be named by two contract paths, and an
entry naming a contract must name the unit it is the contract for.

The file stem must be one of its units (rule 1). **A contract opts out in the manifest, not in
its own prose:** `rule1_exempt = "<reason>"` on a declaring `[[workflows]]` entry — the same
shape as `suite_exempt` in the coverage checker — printed as an exemption on every run. Until
2026-09-09 the opt-out was the string `breaks rule 1` appearing anywhere before `## Identity`,
which cannot be read for polarity: a contract saying that some *other* file breaks rule 1
exempted itself, and so did one that merely quoted the rule.

A manifest naming a contract that does not exist is T1.1's finding, not this one's.

**The check syntax is validated too, since 2026-09-10 (T4.0).** Every numbered item under
`## Acceptance checks` carries exactly one ```` ```check ```` block and every block belongs to
an item, so a check written as prose beside the command that would decide it is reported by its
item number. Each block declares an id unique in the file, a `when` from the vantages above if
it declares one, and no other attribute; `bash -n` must accept it; it must not be empty or
trivially true; and every variable it reads is either in the executor environment above or set
in the block. Both lists are READ from the two `#### ` blocks above rather than retyped in the
validator, and a schema doc declaring neither is reported — otherwise every contract would be
graded against an empty vocabulary and the tree would read clean.

**Actionability is validated too, since 2026-09-10 (T4.1-T4.3).** Each of the five labels
under `#### Outputs fields` must head a bullet in every contract's `## Outputs`, reported as
`outputs-actionability` and READ from that block on the same vacuity guard as the section list
and the check vocabulary. Until that date the gate asserted that a contract named an artifact,
a path, a freshness requirement and a legitimate decline, and asserted nothing whatever about
whether the artifact was for anyone: twelve contracts were green and not one of them named a
beneficiary.

## Status

Written: all 12. `knowledge-digest` (converted to the executable check syntax, 2026-09-10),
`buzz-interactive` (exempt from the check rules — five always-on units, `kind = "service"`),
Marcus's four — `praetorium-daily-plan`, `praetorium-eod-summary`,
`overnight-morning-report`, `weekly-pre-assembly` (T4.1, 2026-09-10) — `augustus-content`,
the one contract two units share (T4.3, 2026-09-10), and Claudius's five —
`standing-research`, `raw-ingest`, `m1-signal-scan`, `bd-stall-radar`, `bd-followup-drafts`
(T4.2, 2026-09-10).

**All twelve carry the five `#### Outputs fields` bullets as of 2026-09-10**, backfilled with
T4.1-T4.3's second half. Eight of the twelve answer `Unknown` for the benefit signal and say why;
four name a signal that is already computable and computed by nothing — `raw-ingest`'s ingest
backlog, `augustus-content`'s board delta, and the Mac-side promotion rate behind
`standing-research` and `weekly-pre-assembly`. That distribution is the finding, and
`outputs-actionability` is what stops it being quietly re-lost.

**Counted under `tomllib` on 2026-09-10**, replacing the 2026-09-01 figures this section
carried while the manifests grew under it: 33 `[[workflows]]` entries, 17 of which carry a
`contract` field, resolving to 12 distinct paths — of which **12 exist**, up from 2. T1.1's
`contract-exists` red list is empty, and `.claude/workflows/ship-dev-plan.js` carries
`MISSING_CONTRACTS = []` to match; the two are joined by
`tests/test_ship_dev_plan_workflow.sh`, so the constant cannot quietly outlive the reds it
names.

`standing-research` is the one contract whose stem is not its unit — the unit is the generic
`agent-proposal`, and the entry carries `rule1_exempt` rather than the file carrying a
disclaimer. Three contracts are exempt from rule 1 in total; the validator names each one and
its reason rather than skipping it silently.

Trajan's platform jobs still carry no
`contract` field at all — a deterministic job promises an artifact and a cadence like any
other, and those are exactly the promises this box breaks silently. Whether they get contracts
belongs with the coverage checker (D6), which must first decide what an entry naming no
contract means.
