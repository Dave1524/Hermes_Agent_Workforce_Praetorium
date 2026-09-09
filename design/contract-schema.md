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
Numbered, each independently decidable, each naming the command that decides it. These
become D3's suite. A check that cannot fail is not a check — assert against what the
system reports, never against a whitelist of things you already expect to be fine.

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

A manifest naming a contract that does not exist is T1.1's finding, not this one's. T4.0 adds
the check syntax.

## Status

Written: `knowledge-digest`. **Corrected 2026-09-01 (W5):** the other 25 entries do *not*
all carry a pointer. Counted under `tomllib`, 14 of the 26 workflow entries have a
`contract` field — marcus 4, claudius 6, augustus 4 — resolving to 13 distinct paths (the
`augustus-content` / `content-change-dispatch` pair shares one, per rule 1). **Trajan's 12
platform jobs carry no `contract` field at all**, which is an omission nobody decided: a
deterministic job still promises an artifact and a cadence, and those are exactly the
promises this box breaks silently. Writing the 12 remaining persona contracts is Phase B,
one brief per owner. Whether the platform jobs get contracts too is open and belongs with
the coverage checker (D6), because the checker must decide what an entry naming no
contract means.
