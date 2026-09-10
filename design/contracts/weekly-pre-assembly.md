# Contract: weekly-pre-assembly

Read on 2026-09-10 from `systemd/weekly-pre-assembly.{service,timer}`,
`bin/run_weekly_pre_assembly_cc.sh`, `profiles/weekly_pre_assembly_cc_task.md`,
`profiles/weekly_pre_assembly.env.example`, `bin/agent_propose.sh`,
`bin/proposal_or_decline.sh`, `bin/deliver_proposal.sh` and `bin/buzz_routes.env`.
`bin/check_deploy_drift.sh` reported `drift: clean` the same day.

**Two things were deliberately not read, and both bound what this contract can claim.**
`~/agent-worktrees/inbox/` is deny-listed for this session — it holds Dave's business
content — so the artifact below is described from the profile's own format block and from
`agent_propose.sh`'s write boundary, never from an example of the real thing. Its directory
was not listed either. `~/.config/agent-workforce/weekly_pre_assembly.env` is likewise
deny-listed; every wiring claim comes from the committed `.env.example` it mirrors, which
matters more here than in the sibling contracts because the most important finding below is
something that example is *missing*.

The checks may still address `$AGENT_INBOX_DIR` — at execution time they run as this job,
against this job's own output. The restriction is on authorship, not on the executor.

## Identity

| | |
|---|---|
| Unit | `weekly-pre-assembly.service` / `.timer` |
| Owner | **marcus** (`design/agents/marcus.toml`) — Hermes-era claudius task; ownership moved 2026-09-01 (registry §7.2) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription, marcus's pointer-skill tree (T3.1) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service`, but see `## Known failure modes` for the one path that bypasses it |

## Trigger

`OnCalendar=Fri 22:00`, `RandomizedDelaySec=5min`, `Persistent=true`. Weekly, ahead of Dave's
own weekend weekly review — the job assembles a pre-read, it does not do the review.

`TimeoutStartSec=45min`, three times the two daily-rhythm jobs' 15. It reads a full week of
daily logs, so the budget is real rather than generous — and it means this job holds the
shared `agent_propose.sh` lock across `bd-stall-radar` at 23:00 whenever it runs long.

The unit also carries `ConditionPathExists=/home/dave/agent-worktrees/inbox`, which is not a
trigger condition so much as a silent off-switch; see `## Known failure modes`.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/vault` mirror — this week's `07_daily/logs/`, `04_operations/key_decisions.md`, `open_loops.md` | clean, within `vault_sync_guard.sh`'s lag budget | **refuse**: gated at `bin/run_weekly_pre_assembly_cc.sh:31`, exits 1 with `REFUSING to run` and *"a pre-read off this tree would be confidently wrong"*. Same 2026-07-23 → 07-27 freeze precedent as the daily-rhythm jobs |
| Notion Task Inbox (this week's completions) | live at run time | proceed and flag under `## Confidence & gaps`, which exists for exactly this: "Notion queries that errored, anything you could not verify" |
| `_inbox/agents/` — existing `<today>_weekly-pre-assembly.md` | this run's date | **stop**: STEP 0 idempotency (`profiles/…:14`). If today's file is already there the run already happened; write nothing, print `skip: today's pre-assembly already exists`. This is a *third* no-file outcome, distinct from both success and decline, and it has consequences recorded below |
| A week with no daily logs at all | — | **decline**: "write NO file and print one line saying why — a clean decline beats a filler proposal" (`:53`) |
| `profiles/weekly_pre_assembly_cc_task.md` (deployed) | readable | runner exits 1 naming the path (`:26`) |
| `~/agent-workforce/skills/marcus/.claude-plugin/plugin.json` | readable | runner exits 1 naming the path (`:29`). Otherwise silent — exit 0, no diagnostic, no skills (T3.1) |

Note the vault is read **from `~/vault` by absolute path**, not from the working directory:
the runner `cd`s to the inbox worktree (`:40`), which contains neither `07_daily/` nor
`04_operations/`. The profile says so at `:17` because getting it wrong yields an empty week
rather than an error.

## Outputs

**This is the only one of Marcus's four workflows in proposal mode**, and every difference
below follows from that. `profiles/weekly_pre_assembly.env.example` sets no `AGENT_RUN_MODE`,
so `agent_propose.sh:167` defaults it to `proposal`.

- **Proposal file** — exactly one, at
  `_inbox/agents/<YYYY-MM-DD>_weekly-pre-assembly.md` in the inbox worktree, carrying the
  six fixed sections of the profile's format block (`Task`, `This week's completions`,
  `This week's decisions`, `Top 3 open loops by leverage`, `Stale or contradicted`,
  `Confidence & gaps`) and `target: vault`, the house convention marking it as a proposed
  vault change rather than send material.
- **Write boundary** — `agent_propose.sh` owns it: nothing outside `_inbox/agents/` may be
  touched, and *"the runner discards any run that writes elsewhere"* (`profiles/…:55`).
- **Commit and push** — proposal mode commits the file to the inbox worktree and pushes to
  the box-safe repo's `agents` branch. Never `main`, never the canonical vault directly.
- **Delivery** — `ExecStartPost=bin/deliver_proposal.sh` (not `deliver_report.sh`, the ops
  jobs' path), `DELIVERY_ROUTE=research` → channel `6ea596af-248f-46ee-b89d-8b13696083e4`,
  **event kind 45001**, notify **claudius** (`bin/buzz_routes.env:46-48`), subject
  `[Praetorium] Weekly pre-assembly`. Anchored by
  `DELIVERY_RUN_MARKER=/home/dave/logs/run-markers/%n`.

  **The notify target is claudius while the owner is marcus.** That is the residue of the
  2026-09-01 ownership move — the workflow changed hands, the route did not. Recorded as an
  observation rather than asserted as correct: routing the weekly pre-read to the Head of
  Research may well be deliberate. It is named here because a reader comparing owner against
  notify will otherwise assume one of the two is a bug.

- **No Notion row and no receipt.** The proposal file is the artifact.

- **Beneficiary:** Dave, ahead of the weekly assembly. The route notifies claudius while the
  owner is marcus (see above) — the *reader* is Dave either way.
- **Next actor:** Dave, from the Mac.
- **Next action:** review the proposal in the Notion Agent Inbox and promote it into the vault
  or drop it. The commit on the `agents` branch is not a vault change until he merges it.
- **Benefit hypothesis:** the week's open loops and stale items are enumerated before the
  assembly, so the assembly spends its time deciding rather than recalling.
- **Benefit signal:** the promotion decision — a proposal merged Mac-side is evidence it was
  read. That decision is visible in the canonical vault's history and in nothing on this box,
  so it is a real signal that is currently unmeasured here rather than an absent one.

## Decline conditions

**Two legitimate no-file outcomes, and neither emits the sentinel the tooling reads.**

1. **A week with no daily logs** — `profiles/…:53`: *"If the week has no daily logs at all
   (nothing to assemble), write NO file and print one line saying why — a clean decline beats
   a filler proposal."*
2. **Today's file already exists** — STEP 0, `:15`: *"write nothing and stop (print one line:
   `skip: today's pre-assembly already exists`)"*. This is the `Persistent=true` catch-up and
   manual-rerun path.

`bin/proposal_or_decline.sh` — the shared verifier for every proposal-mode job — accepts a run
only if it produced this run's dated proposal **or** this run's attempt log matches
`^DECLINE:` (`:decline_sentinel`). Neither instruction above produces that prefix. The profile
asks for "one line saying why" and for the literal string `skip: …`; nothing tells the agent to
write `DECLINE:`.

`bin/deliver_proposal.sh:37` reads the same prefix to render the message, falling back to
`DECLINE: no reason recorded in $ATTEMPT_LOG` (`:50`) — so even the delivery Dave sees loses
the reason, and the correct explanation the agent printed is discarded.

This is not currently *failing*, and the reason is worse than if it were; see the first entry
under `## Known failure modes`.

## Side effects

- Writes one file under `_inbox/agents/` in `~/agent-worktrees/inbox`, then commits and pushes
  it to the box-safe repo's `agents` branch (proposal mode, `agent_propose.sh`).
- Touches `~/logs/run-markers/weekly-pre-assembly.service` (`ExecStartPre`).
- Appends to `~/agent-workforce/logs/agent_run.log`,
  `logs/last-attempt/weekly-pre-assembly.log`, `cost.log`, and one line to
  `~/logs/delivery-receipts.jsonl`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, for up to 45 minutes.
- Runs with cwd `$HOME/agent-worktrees/inbox` (`run_weekly_pre_assembly_cc.sh:40`).

Reads `~/vault` and never writes it — on any branch. Never touches `~/dev/*`. Never acts
outward: `profiles/…:71` — *"This task never emails, posts, DMs, shares, or messages anyone —
Notion reads only, Discord delivery is the run notification."*

## Acceptance checks

Eight checks. Five `run`, three `sweep`. Unlike the three ops siblings there is no receipt and
no artifact-sha delivery comparison against a report glob — the artifact is a dated file whose
name this job controls, which makes it easier to assert and is the one way proposal mode is
simpler than ops mode.

1. **This run produced its dated proposal, or a real decline sentinel.** The same disjunction
   `proposal_or_decline.sh` encodes, asserted here because — per `## Decline conditions` —
   **this job is not currently wired to that script at all**. Written to fail on today's box:
   both documented no-file paths print prose without the prefix, so a legitimately declining
   run goes red until either the profile emits `DECLINE:` or this check learns the two literal
   strings. Red for a real reason beats green for none.

   ```check id=proposal-or-decline
   f="$AGENT_INBOX_DIR/${RUN_DATE}_weekly-pre-assembly.md"
   if [ -f "$f" ] && [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 \
        -name "${RUN_DATE}_weekly-pre-assembly.md" -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]; then
     echo "proposed ${RUN_DATE}_weekly-pre-assembly.md"; exit 0
   fi
   [ -f "$AGENT_ATTEMPT_LOG" ] || { echo "no proposal and no attempt log"; exit 1; }
   [ -n "$(grep -E '^DECLINE:' "$AGENT_ATTEMPT_LOG")" ] \
     || echo "no proposal this run, and the attempt log carries no ^DECLINE: sentinel"
   [ -n "$(grep -E '^DECLINE:' "$AGENT_ATTEMPT_LOG")" ]
   ```

2. **Exactly one proposal, not two.** The profile says "exactly ONE proposal file" (`:51`) and
   STEP 0 exists to keep a catch-up run from stacking a second. Asserted by counting this
   job's files for this date rather than trusting the idempotency instruction.

   ```check id=exactly-one-proposal
   n="$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_weekly-pre-assembly*.md" 2>/dev/null | wc -l)"
   [ "$n" -le 1 ] || echo "$n files for $RUN_DATE — STEP 0 idempotency did not hold"
   [ "$n" -le 1 ]
   ```

3. **The proposal carries the six sections the format block fixes.** The inbox tooling and
   Dave's review both read by section; a pre-read missing `## Confidence & gaps` is one that
   silently dropped the days it could not cover, which is the section that exists to prevent
   exactly that.

   ```check id=proposal-has-its-sections
   f="$AGENT_INBOX_DIR/${RUN_DATE}_weekly-pre-assembly.md"
   [ -f "$f" ] || { echo "n/a: no proposal this run"; exit 77; }
   missing=
   for s in "## Task" "## This week's completions" "## This week's decisions" \
            "## Top 3 open loops by leverage" "## Stale or contradicted" "## Confidence & gaps"; do
     grep -qF "$s" "$f" || missing="$missing [$s]"
   done
   [ -z "$missing" ] || echo "missing sections:$missing"
   [ -z "$missing" ]
   ```

4. **The proposal declares its target.** `target: vault` is what marks this as a proposed vault
   change rather than send material; `bd-followup-drafts` writes `target: none` for the
   opposite reason. A proposal with no target line is one the promote pass cannot route.

   ```check id=proposal-declares-target
   f="$AGENT_INBOX_DIR/${RUN_DATE}_weekly-pre-assembly.md"
   [ -f "$f" ] || { echo "n/a: no proposal this run"; exit 77; }
   grep -qE '^target: *vault' "$f" || echo "no 'target: vault' line — the promote pass cannot route this"
   grep -qE '^target: *vault' "$f"
   ```

5. **The write boundary held.** Proposal mode's central promise, and the reason the runner may
   `cd` into a worktree holding Dave's business content at all. `agent_propose.sh` discards a
   run that writes outside `_inbox/agents/`; this asserts the outcome rather than the intent,
   from git's own view of the worktree.

   ```check id=write-boundary-held
   [ -n "${INBOX_WORKTREE:-}" ] || { echo "n/a: no inbox worktree in scope"; exit 77; }
   out="$(git -C "$INBOX_WORKTREE" diff --name-only "HEAD~1..HEAD" 2>/dev/null \
            | grep -v '^_inbox/agents/')"
   [ -z "$out" ] || echo "wrote outside _inbox/agents/:$out"
   [ -z "$out" ]
   ```

6. **The vault guard ran and passed.** Present, not merely un-refused —
   `vault_sync_guard.sh check` prints `OK:` on every success path (`:129`, `:137`), so silence
   means it never ran, which looks identical to a pass.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

7. **The unit actually ran this week — it was not skipped by its own `ConditionPathExists`.**
   `sweep`. A failed condition makes systemd mark the unit as *skipped*: it exits 0, sets no
   failure state, and **does not fire `OnFailure`**, so `agent-alert@` never runs and the
   weekly pre-read simply stops appearing. `ConditionResult=no` is the only place that is
   recorded.

   ```check id=not-condition-skipped when=sweep
   r="$($SYSTEMCTL show "$UNIT.service" -p ConditionResult --value)"
   [ "$r" != no ] || echo "ConditionPathExists failed — the inbox worktree is missing and the unit was silently skipped"
   [ "$r" != no ]
   ```

8. **The timer fired within its own cadence, and was not silently lock-skipped.** `sweep`.
   Eight days: weekly, plus the 5-minute jitter, plus slack for a late `Persistent=true`
   catch-up. This is the longest window of Marcus's four, which is also what makes it the
   weakest signal — a missed Friday is invisible for a week by construction, so
   `not-condition-skipped` above is the earlier tell.

   ```check id=timer-fired-and-not-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 691200 ] || { echo "last fired $(( ( $(date +%s) - ${t#@} ) / 86400 ))d ago"; exit 1; }
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

## Known failure modes

- **This job has no `AGENT_VERIFY_CMD`, and it is the only scheduled job on the box without
  one — in either mode.** Counted across all ten `profiles/*.env.example` on 2026-09-10: nine
  set `AGENT_VERIFY_CMD`, this one does not. `profiles/weekly_pre_assembly.env.example` sets
  `AGENT_PROFILE`, `AGENT_OWNER`, `AGENT_TASK_SLUG`, `AGENT_MAX_ATTEMPTS` and
  `AGENT_RUNTIME_CMD` — and stops there. Its five proposal-mode siblings (`standing_research`,
  `raw_ingest`, `knowledge_digest`, `bd_stall_radar`, `bd_followup_drafts`) wire
  `bin/proposal_or_decline.sh <slug>`; the three ops jobs wire a `find` over their artifacts. So a run that produces nothing — a provider error that becomes the agent's
  final response, the 2026-07-21 shape — exits 0 and logs clean, which is verbatim the ten-day
  silent-failure regression `proposal_or_decline.sh` was written to close (see its header). The
  one job it was never wired into is this one.
  **Caveat, and it is the important half:** the live env at
  `~/.config/agent-workforce/weekly_pre_assembly.env` is deny-listed and was not read, so the
  live file may well set it. What is established is that the committed example — the file the
  install instructions say to copy, and the only version any reader can check — does not.
  Either way that is a defect: if the live file has it, the example is wrong and the next
  install loses it. Signal: `proposal-or-decline`, which asserts the obligation from the
  contract regardless of what the env wires.
- **Both documented decline paths emit prose, not the sentinel.** `profiles/…:53` asks for
  "one line saying why"; STEP 0 at `:15` asks for `skip: today's pre-assembly already exists`.
  `proposal_or_decline.sh` matches `^DECLINE:` and nothing else. So the moment the previous
  finding is fixed by wiring the verify command, **every legitimate decline starts failing the
  run** and burning `AGENT_MAX_ATTEMPTS=2` before alerting Dave about a week that correctly had
  nothing to assemble. The two defects mask each other: unwired, dead runs pass; wired,
  correct declines fail. Fixing one without the other trades a silent failure for a noisy
  false one. The profile must emit `DECLINE: <reason>` — that is the smaller change, and it
  also restores the reason to Dave's delivery message, which `deliver_proposal.sh:50`
  currently replaces with `DECLINE: no reason recorded`.
- **`ConditionPathExists` is a silent off-switch.** If `/home/dave/agent-worktrees/inbox` is
  missing — a worktree pruned, a `gitdir:` pointer broken by the `~/vault` symlink resolution
  trap, a disk not mounted — systemd marks the unit *skipped*, not failed. Exit 0, no
  `OnFailure`, no alert, no artifact, and the weekly pre-read stops arriving with nothing
  anywhere saying why. Signal: `not-condition-skipped`, reading `ConditionResult`, which is the
  only record of it.
- **It holds the shared lock across `bd-stall-radar`.** 22:00 Friday with a 45-minute timeout
  against a 23:00 neighbour: a run using its full budget is still holding
  `${AGENT_PROPOSE_LOCK}` when the radar fires, and the radar then exits 0 having logged
  `SKIP: previous run still active` (`bin/agent_propose.sh:144`) — no alert, no artifact. The
  cost of this job running long is paid by a *different* job, on a Friday night, invisibly.
  Signal for the victim is `bd-stall-radar`'s own `not-lock-skipped`; there is nothing to
  assert from this side, which is why it is recorded rather than checked.
- **Owner and notify disagree.** Owner marcus, route `research` → notify claudius, kind 45001.
  A residue of the 2026-09-01 ownership move (registry §7.2) — or a deliberate routing of the
  weekly pre-read to the Head of Research. Not asserted either way; named so the next reader
  does not have to rediscover the discrepancy to decide it is intentional.
- **The artifact is described, never inspected.** `~/agent-worktrees/inbox/` was not read or
  listed while writing this contract, so every claim about the proposal's shape comes from the
  profile's format block and from `agent_propose.sh`'s boundary — the specification, not an
  instance. If the produced files diverge from that block, this contract's
  `proposal-has-its-sections` check is what will say so, and it will be the check that is
  right.
