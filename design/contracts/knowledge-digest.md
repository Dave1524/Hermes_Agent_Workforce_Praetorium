# Contract: knowledge-digest

Worked example for `design/contract-schema.md`. Everything below was read on 2026-09-01
from `systemctl cat knowledge-digest.service`, `bin/run_knowledge_digest_cc.sh`,
`profiles/knowledge_digest_cc_task.md` and `bin/proposal_or_decline.sh`.

## Identity

| | |
|---|---|
| Unit | `knowledge-digest.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription |
| Contract version | 1 (2026-09-01) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Sun 09:00`, `RandomizedDelaySec=5min`. Recurring; no expiry.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/vault` mirror (`05_knowledge/`, `11_entities/`) | must be clean and current — the digest is a 7-day git-log delta over it | **refuse**: `bin/vault_sync_guard.sh check` runs before the model starts and exits 1 with a loud message. A digest off a frozen mirror is a confident wrong answer |
| `~/vault/04_operations/open_loops.md` | same mirror, same guard | covered by the guard above |
| `~/agent-worktrees/inbox` worktree | checked out fresh by `agent_propose.sh` before the run | runner fails before the model starts |
| `profiles/knowledge_digest_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named |
| existing `_inbox/agents/<today>_knowledge-digest.md` | today's date | **skip**: STEP 0 idempotency — prints `skip: today's knowledge-digest already exists` and writes nothing |

The 7-day window is computed with `git log --since='7 days ago'`, explicitly **not** file
mtimes, which are unreliable across a re-clone or resync.

## Outputs

- **Artifact:** exactly one file, `_inbox/agents/<YYYY-MM-DD>_knowledge-digest.md`, in the
  inbox worktree. Body **under 500 words** — it is a pointer digest, not a re-summary.
- **Header must state** that this is the *knowledge* digest (git-log delta over
  `05_knowledge/` + `11_entities/`) and does **not** replace `weekly-pre-assembly`, which
  is the *activity* pre-read. Two adjacent weekly reports that do not say how they differ
  is how one gets read as the other.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=research` →
  channel `6ea596af-…`, **event kind 45001** (forum), notify `claudius`. A kind-9 post
  into that channel is receipted `ok` and shown to nobody.
- Downstream: the proposal syncs to the Notion Agent Inbox and is Mac-gated for approval.

## Decline conditions

Exactly one legitimate decline: **no `05_knowledge/` or `11_entities/` paths changed in
the window.** The run then prints, verbatim and as its own line:

```
DECLINE: no 05_knowledge/ or 11_entities/ changes in the last 7 days
```

and writes no file. `bin/proposal_or_decline.sh knowledge-digest` matches `^DECLINE:` in
the last 40 lines of the run log and exits 0.

The idempotency skip in STEP 0 is **not** a decline — it prints `skip: …` and no artifact,
so `proposal_or_decline.sh` fails the run. That is correct today (a second run in one day
is anomalous and should be visible) but it means a manual re-run on a Sunday reads as a
failure. Recorded so it is a known behaviour rather than a surprise.

## Side effects

- Checks out / resets `~/agent-worktrees/inbox`.
- Commits the proposal and pushes to the box-safe repo's `agents/inbox` branch.
- Writes a run record to `~/agent-workforce/logs/agent_run.log` and a cost line to
  `cost.log`; writes `memory=no-store` because `AGENT_PROFILE` is `claude-opus`, a model
  name with no `~/.hermes/profiles/` store (registry §6.6).
- Touches `/home/dave/logs/run-markers/knowledge-digest.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.
- Delivery receipt appended by `bin/deliver.sh`.

Nothing else. The runner discards any run that writes outside `_inbox/agents/`, and the
task never writes `~/vault` directly on any branch.

## Acceptance checks

1. **Artifact exists and is this run's.** `_inbox/agents/<RUN_DATE>_knowledge-digest.md`
   is present and newer than `AGENT_RUN_STARTED_AT` — `bin/proposal_or_decline.sh
   knowledge-digest` (already wired as `AGENT_VERIFY_CMD`).
2. **Or a decline was declared**, `^DECLINE:` in the last 40 log lines. Same command; the
   check must assert **which branch passed**, never merely that the command exited 0.
3. **Body is under 500 words.** `wc -w` on the file body.
4. **Header carries the weekly-pre-assembly disclaimer** — `grep -q 'weekly-pre-assembly'`.
5. **Write boundary held**: `git -C ~/agent-worktrees/inbox diff --name-only HEAD~1` lists
   only paths under `_inbox/agents/`.
6. **Every path cited in the digest exists in the mirror**, or is explicitly named under
   *Confidence & gaps* as renamed/removed within the window.
7. **The run was not silently skipped**: the run log for this trigger does **not** contain
   `SKIP: previous run still active`. Without this, a lock collision reads as a clean night
   (`agent-model.md` §6.6).
8. **The timer actually fired this week**: the unit's `LastTriggerUSec` is within 8 days.
   Assert against systemd, not against a report that says it ran.
9. **The vault guard ran and passed** — the refusal message is absent from the run log.

Checks 7–9 are the ones that catch the failures this box actually produces; 1–6 catch a
bad digest. D3 needs both.

## Known failure modes

- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging `SKIP: previous run
  still active`. No alert, no artifact, and `OnFailure` never fires because nothing
  failed. Signal: check 7.
- **Stale mirror.** Guarded — this is the one already closed by
  `bin/vault_sync_guard.sh check`, and the reason the guard exists.
- **Provider death reading as a clean no-op.** The ancestor failure: an OpenRouter 402
  killed the hermes/claudius path for ten days while logging *"OK: run completed, agent
  produced no proposal"*, because the error went to the profile's own `errors.log` and
  never reached the attempt's stdout. `proposal_or_decline.sh` was written for exactly
  this and closes it — a run that produces neither artifact nor sentinel now fails.
- **Confusion with `weekly-pre-assembly`.** Both are weekly, both land in the research
  route, both are pre-reads. Mitigated by the mandatory header line; check 4.
- **Kind mismatch on delivery.** The research route is a forum (45001). A producer
  publishing kind 9 there is receipted `ok` and invisible. Not currently possible for this
  job — `deliver.sh` reads the kind from the route table — but it is the failure this
  route has already produced once, from a different producer.
- **Midnight rollover.** `RUN_DATE` and `AGENT_RUN_STARTED_AT` are exported once by
  `agent_propose.sh` and read, never recomputed, so a run spanning midnight cannot
  disagree with itself about which file it was supposed to write.
