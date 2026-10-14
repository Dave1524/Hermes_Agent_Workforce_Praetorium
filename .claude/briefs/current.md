# Brief: Event-driven board reactor
**Date:** 2026-10-13   **Verify:** `bash bin/verify.sh` (repo root, run detached, ~10 min); UI: `cd ui/control-room && npx tsc -p tsconfig.json --noEmit && npx vitest run`; `bash tests/test_control_room_spa.sh` after `bin/control_room_build_ui.sh`.
**Input:** `.claude/briefs/board-event-driven-requirements.md`. **Supersedes:** `archive/2026-10-13-board-24-7-schedule-and-card-time.md` (hourly timers); its card-time criteria 1-4 carry over below.

## Acceptance criteria
1. **Edge latency.** A card created, a brief or answer note written, or a board decision signed starts the right run within 5 s when a slot is free. No timer tick involved.
2. **Second path.** `board-reconcile.timer` (every 5 min, 24/7) runs the same observe/plan/apply as the daemon (`board_reactor.py --once`). Kill the daemon: no card is lost; the reconcile picks it up and receipts the daemon as `permanent` unless the operator stopped it from the Control Room.
3. **Supervision.** `board-reactor.service` is `Type=notify`, `WatchdogSec=60`, `Restart=on-failure`, `RestartSec=5`, `RestartSteps=6`, `RestartMaxDelaySec=300`, `StartLimitIntervalSec=1h`, `StartLimitBurst=10`, `OnFailure=agent-alert@%n`. A hung loop (`kill -STOP`) is killed by the watchdog and restarted.
4. **Error classes with reason codes** on every reactor receipt: `transient` (requeue with backoff), `poison` (the card is quarantined: a `held` ledger event by actor `reactor`, the card derives to Blocked with the reason code; Dave's `unblock` releases it), `permanent` (the reactor exits non-zero with the reason; systemd restarts; StartLimit raises the alert).
5. **Bounded parallel (D1).** At most `BOARD_REACTOR_MAX_RUNS` (default 2) board runs at once; never two runs on one card. Runs are per-card template units `board-brief@<id>.service` and `board-work@<id>.service`.
6. **24/7 (D2).** No weekday or office-hour window anywhere in the board path.
7. **Daily cap (D4).** `BOARD_REACTOR_DAILY_CAP` model runs per box-local day. At the cap further runs are held as `capped`, one `[incident]` is raised, and runs resume after local midnight or when the cap is raised.
8. **Loop protection (D5).** Per-card cooldown between runs (`BOARD_REACTOR_COOLDOWN`, default 10 min); after 3 failed attempts on one card it is quarantined (criterion 4); the existing two-strike Blocked rule (`board.py:315-317`) is unchanged.
9. **Card time.** `research_on` accepts `YYYY-MM-DD` (00:00) or `YYYY-MM-DDTHH:MM`, box-local (Europe/Amsterdam). A bad time is refused like a bad date. A Todo card is `scheduled` until `now >= research_on` to the minute; the daemon sleeps until the earliest due time and starts it within 1 min. `research_on` after `deadline` refused (compare the date part). The popup uses a date-and-time control and shows `2026-10-14 06:30` (date-only stays a date).
10. **Delete (D3).** Delete is a signed broker decision `deleted`, no reason prompt, offered in every column except In Review (where Reject stays). It stops any active run, hides the card from every column and moves it to `$BOARD_ROOT/trash/<id>/`. A signed `restore` within 30 days brings it back; the reconcile purges trash older than 30 days. Withdraw leaves the UI; existing withdrawn cards stay Done/withdrawn. `unapplied` keeps the decisions of a trashed card; `mark_pages` marks withdrawn and deleted pages.
11. **Idea merged into brief.** A card is a title plus a brief. Create takes title + brief text; the text is brief v1 by `dave`. The id is `slugify(title)`; a collision is refused. `idea` is gone from every site. A one-time `board.py migrate-idea` turns each existing `idea` into a v1 brief event; idempotent on re-run.
12. **The agent asks first (D7).** The brief run reads v1 and either posts a `questions` note (card waits in Refine, labelled "questions for you") or records "no open questions" and writes v2. Dave's answer note wakes the reactor and the agent writes v2 for approval. At most 2 question rounds; the third run must write v2.
13. **Generic sources (D8).** The reactor runs registered sources behind one interface (`name`, `wake_paths()`, `observe()`, pure `plan(state, now, budget)`, `apply(action)`). The board is the only source; the cap and N are the reactor's budget, shared across sources.
14. **Only one picker.** `research-brief.{service,timer}` retires through the `control-room/*` retirement PR flow; agent-proposal's `--column todo` pick is removed (it keeps its standing missions). `tests/test_workflow_coverage.py:583-633` stays green.
15. **Incidents do not storm.** `incident_notify.py` opens an incident only after a verdict is red for `INCIDENT_OPEN_AFTER` (default 15 min) or 3 consecutive red verdicts, and sends `[recovered]` only after green for a hold period. A reactor restart storm pages at most once.
16. **Visible and controllable.** The reactor appears in the Control Room; Stop is its pause (the reconcile treats an operator stop, proven by the broker receipt, as paused, not dead). Each `board-*@<id>` instance can be stopped. The card shows "approved, awaiting Mac" between approval and merge (D6).

## Files to modify
- `bin/board.py` — `research_on` datetime; `held` event (actor `reactor`) and its Blocked derivation; `deleted`/`restored` handling and trash; `unapplied` keeps trashed cards; drop `idea` (create takes brief text); `migrate-idea`; `pick --card <id>`.
- `bin/board_land.py` — `mark_pages` withdrawn and deleted.
- `bin/control_broker.py`, `bin/control_room_board_decisions.py`, `bin/control_broker_allowlist.py` — verbs `delete` and `restore` (no reason); grammar for a single-instance system service and for `board-*@` instances (stop).
- `bin/control_room_board_writes.py`, `bin/control_room_board.py` — create with title + brief; no `idea`; trash listing for Restore.
- `bin/agent_propose.sh` — `AGENT_BOARD_CARD`; lock narrowed per step 1's audit.
- `bin/incident_notify.py`, `bin/workflow_incidents.py` — debounce and hysteresis.
- `buzz-team/buzz-team-mcp.py` — `board_*` tools without `idea`.
- `profiles/research_brief_cc_task.md`, `profiles/research_brief.env.example`, `profiles/standing_research.env.example` (drop the pick), `design/contracts/research-brief.md`.
- `design/agents/claudius.toml`, `config/fleet-units.tsv`, `bin/buzz_producers.tsv`, `design/fleet-suites.toml`, `docs/runbook.md` (§ Board reactor: operation, pause, hand install, reason codes).
- `tests/test_receipt_coverage.py` (producer class `reactor`, template kind, tally), `tests/test_control_room_views.py:30`, `tests/test_receipt_coverage.py:41,174`, `tests/test_workflow_coverage.py:367` (count literals).
- UI (`ui/control-room/src/`): `model/card.ts`, `model/cardDraft.ts`, `api/schemas/board.ts`, `components/card/*` (`CardIdea.tsx` removed; `CardBrief`, `CardFooter` Delete, `CardSidePanel` datetime, questions note, awaiting Mac), `components/dialogs/CardDialog.tsx`, a trash view with Restore, fixtures; then `bin/control_room_build_ui.sh`.

## Files to create
- `bin/reactor_source.py` — the source interface and action types.
- `bin/board_plan.py` — pure plan for the board source.
- `bin/board_reactor.py` — daemon and `--once`; state in `$BOARD_ROOT/reactor/state.json` (attempts, cooldowns, day count), written atomically; heartbeat file.
- `bin/inotify_watch.py` — ctypes inotify (no library on the box); a watch per card dir (inotify is not recursive), on `cards/` and on the decisions file.
- `bin/sd_notify.py` — `READY=1`, `WATCHDOG=1`, `STATUS=` over `NOTIFY_SOCKET` with stdlib `socket`.
- `systemd/board-reactor.service`, `systemd/board-reconcile.{service,timer}`, `systemd/board-brief@.service`, `systemd/board-work@.service`.
- `profiles/board_reactor.env.example`, `profiles/board_work.env.example`.
- `design/contracts/board-reactor.md`, `design/contracts/board-reconcile.md`.
- Tests: `tests/test_board_plan.py`, `tests/test_board_reactor.py` (temp `BOARD_ROOT`, fake `systemctl`, fake `NOTIFY_SOCKET`), `tests/test_inotify_watch.py`, `tests/test_incident_debounce.py`, `.sh` gate wrappers.

## Order of work

Each step test-first, red then green.
1. **Audit the fleet lock.** What does `/tmp/agent_propose.lock` serialise today (inbox worktree git, `vault_sync_guard.sh`, shared scratch)? Write the answer into Notes below. Each shared resource gets its own narrow lock before board runs leave the fleet lock.
2. Card time in `board.py` (criterion 9).
3. `board_plan.py` table tests: every trigger in the table below, each error class, cap, cooldown, attempt limit, N, delete, restore, purge, two-strike, questions rounds.
4. Ledger: `held`, trash, `unapplied`, `mark_pages`.
5. Broker verbs `delete`/`restore` and allowlist render; `test_control_broker_board.py`.
6. Idea into brief: migration plus every site (board, seam, bridge, profiles, contract); D7's questions loop in the brief profile.
7. `inotify_watch.py`, `sd_notify.py`, `board_reactor.py`.
8. Units, profiles, contracts, manifest, fleet-units, producers, receipt class, count literals.
9. Incident debounce.
10. UI and rebuild.
11. Retire research-brief through `bin/workflow_pr.py`; drop agent-proposal's pick.
12. Runbook and suite anchors; full `bin/verify.sh`. Report deploy drift for the new units as expected (Dave hand-installs after merge).

## Test plan
- `plan()` is the gate: one table row per trigger and class, boundaries to the minute for `research_on`, N and cap at the edge.
- Reactor integration against a temp root: create a card dir and see `systemctl start board-brief@<id>` within one wake; append a decision line and see `board-work@`; a fake `systemctl` failure classified transient; a poison card held after 3 attempts; restart with state on disk and no duplicate start.
- Watchdog: a test that the loop pings `WATCHDOG=1` at under half of `WATCHDOG_USEC`.
- Broker: signed `deleted`/`restored`, verify with `board_decision_sig.py`; no reason accepted.
- Receipt coverage, workflow coverage and views tests green with the new rows.
- UI: create with brief only, Delete without prompt, Restore, datetime round trip, questions note; vitest count up, none removed.
- Live on the box after hand install: the six checks in Verification below.

## Triggers
| Trigger | Latency | On failure | Idempotency | Observed by | Grows |
|---|---|---|---|---|---|
| Card created, brief or answer note | ≤ 5 s | reconcile, every 5 min | one `board-*@<id>` unit per card; pick by run id | run receipt; reactor flips | one wake per write |
| Decision signed (`decisions.jsonl`) | ≤ 5 s | reconcile | decision id; re-derive under the card lock | same | one wake per decision |
| `research_on` reached | ≤ 1 min | reconcile | same | same | — |
| Slot freed, cap reset at midnight | ≤ 5 s | reconcile | same | same | — |
| Delete / restore | ≤ 5 s | reconcile finishes the move | decision id; a completed move is a no-op | decision stream, trash | trash, purged at 30 days |
| Daemon dead or hung | watchdog 60 s; backoff 5 s to 5 min | StartLimit: `OnFailure` alert plus the reconcile's `permanent` receipt | — | receipt, debounced incident | — |

## Out of scope / do not touch
- The cron jobs other than removing agent-proposal's Todo pick.
- The Mac-side B10 watcher. Requirement recorded for it (D6): on wake, replay unapplied signed approvals and merge.
- Inbox and approvals as reactor sources (the interface exists; no second source).
- Crypto-shredding or legal erasure.
- Installing or enabling units: Dave hand-installs after merge, root files by hand as the runbook says.

## Risks
- **Parallel vault writes.** Two runs at once may contend on the inbox worktree. Tell: git lock errors in a run receipt. Response: step 1's narrow lock; never widen back to the fleet lock silently.
- **Inotify watch limits.** One watch per card. Tell: `ENOSPC` from `inotify_add_watch`, classed `permanent` with reason `inotify-limit`. The reconcile still covers every card.
- **Rate limits.** N runs plus the 03:30 standing research share the subscription. A 429 is `transient`; a spend-cap 429 is `permanent` (it does not clear on retry).
- **Receipt growth.** The reactor receipts flips only; the reconcile is one row ending on `receipt_finish`.

## Design research
1. **Level-triggered reconcile, with edges only as a wake-up.** Controllers are level-driven; events wake the loop, Reconcile reads full state, periodic resync catches missed events, per-item rate-limited requeue, terminal errors stop retries. Fits because the board derives every column from the ledger. https://kubernetes.io/docs/concepts/architecture/controller/ · https://github.com/kubernetes/community/blob/master/contributors/devel/sig-api-machinery/controllers.md · https://pkg.go.dev/k8s.io/client-go/util/workqueue · https://pkg.go.dev/sigs.k8s.io/controller-runtime/pkg/reconcile · https://hackernoon.com/level-triggering-and-reconciliation-in-kubernetes-1f17fe30333d
2. **Outbox and idempotent consumer.** The append-only ledger is the outbox; the pick's run id is the dedup key (`board.py:619-622`). https://microservices.io/patterns/data/transactional-outbox.html · https://microservices.io/patterns/communication-style/idempotent-consumer.html
3. **Supervision.** OTP restart intensity; systemd `Restart`, `RestartSteps`/`RestartMaxDelaySec` (254+, box has 259), `StartLimit*`, `WatchdogSec` with `sd_notify`; inotify is not recursive and path units go failed past `TriggerLimitBurst`, which is why the daemon owns its watches. https://www.erlang.org/doc/system/sup_princ.html · https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html · https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html · https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html
4. **Poison messages.** Delivery-count dead-lettering with a reason; an allow-list of retryable errors; Anthropic's error table. Quarantine here is a derived Blocked state with a reason, not a separate queue. https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html · https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues · https://docs.celeryq.dev/en/stable/userguide/tasks.html · https://platform.claude.com/docs/en/api/errors
5. **Bursts and caps.** One run per key plus a global limit; pause rather than drop. https://docs.github.com/en/actions/using-jobs/using-concurrency · https://docs.temporal.io/schedule · https://github.com/sidekiq/sidekiq/wiki/Ent-Rate-Limiting · https://platform.claude.com/docs/en/api/rate-limits
6. **Delete in an append-only, signed log.** Compensating or tombstone events keep the audit trail; archive and prune rather than a soft-delete flag; trash with a retention window. https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing · https://event-driven.io/en/gdpr · https://brandur.org/soft-deletion
7. **Alert debounce.** A sustained-condition hold before opening, a hold before clearing, hysteresis. https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/ · https://prometheus.io/docs/alerting/latest/configuration/ · https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/flapping.html

## Decisions for Dave (all decided 2026-10-13)
- **R0 Reactor shape:** long-running daemon (`Type=notify`, inotify, watchdog, backoff) plus the reconcile timer. Not the path-unit doorbell.
- **D1 Burst:** bounded parallel; N configurable, default 2; per-card template units.
- **D2 Quiet hours:** none; 24/7.
- **D3 Delete:** signed tombstone, trash for 30 days, signed restore.
- **D4 Daily cap:** cap with one alert when it is hit; resume at local midnight.
- **D5 Loop protection:** cooldown, 3-attempt quarantine, existing two strikes.
- **D6 Mac asleep:** merge on wake (Mac-side B10 requirement).
- **D7 Brief authoring:** the agent asks first, at most 2 rounds.
- **D8 Scope:** generic sources; the board is the first.

## Notes
### Step 1 — what `/tmp/agent_propose.lock` serialises (audited 2026-10-14)
Every `agent_propose.sh` run takes it (`flock -n`, overlap = receipted SKIP). What it actually protects:
1. **The inbox worktree** (`~/agent-worktrees/inbox`): card-less proposal runs checkout/pull, let the model
   write `_inbox/agents/`, then commit/push or `reset --hard`; `refresh_scorecard` (every run's exit)
   pulls, adds and commits the metrics digest there. Card runs (research on a card) only *read* it:
   the post-run dirty check and the failure-path `reset --hard`. Under parallelism that check would see
   a concurrent proposal run's work and reset it. **Narrow lock:** `AGENT_INBOX_LOCK`
   (default `/tmp/agent_inbox.lock`), held exclusively by card-less proposal runs from checkout to exit;
   `refresh_scorecard` takes it `-n` and skips when busy (the holder refreshes on its own exit). Card and
   brief runs never touch the worktree: no dirty check, no reset; the guarantee moves into the unit
   (`ReadOnlyPaths=` over the worktree and both vault clones), enforced by the namespace, not detected after.
2. **`last-attempt/<task>.log` and `<task>.usage.json`**, keyed by task slug: two runs of one slug clobber
   each other's verify input and usage. **Per instance:** the template units set `AGENT_ATTEMPT_LOG` and
   `AGENT_USAGE_JSON` with `%i`, so `agent_propose.sh` and the `ExecStartPost` hook read the same file.
3. **Shared logs** (`cost.log`, `agent_propose.log` — single `printf >>` lines under PIPE_BUF, atomic with
   O_APPEND; `agent_run.log` — a whole attempt `cat >>`, can interleave): `agent_run.log` appends take a
   short `flock` on `agent_run.log.lock`.
4. Not shared: card ledgers (own `card_lock`), receipts (per run id), Claude sessions (per session id),
   run markers (per unit `%n`), `RUN_DATE` (per run), the vault mirror (`vault_sync_guard.sh check` is
   read-only; the writer `qmd-refresh` never took this lock).
**Result:** a run with `AGENT_BOARD_CARD` set skips the fleet lock and takes a per-card lock
(`/tmp/agent_board_card_<id>.lock`, `-n`; the reactor already never starts two runs on one card).

### Shared contract (forks build against this)
- `board.py`: `DECISIONS` += `deleted`, `restored` (no reason). `EVENTS` += `held` (actor `reactor` only,
  `fields.reason` = a reason code). `MOVES`: `delete` in every column except In Review; `withdraw` gone.
- Trash: the reactor moves `cards/<id>` to `trash/<id>` after a `deleted` decision and back after a later
  `restored` within 30 days. `board.trash_list(root) -> [{id, title, deleted_at, purge_after}]`, newest first.
  `create` refuses an id present in `cards/` or `trash/`.
- `create_card(root, args)`: `args.title`, `args.brief` (path, required), `scope`, `kind`, `owner`, `priority`,
  `deadline`, `research_on`, `tags`, `actor`. No `id`, no `idea`.
- View adds `awaiting_answer` (bool: the newest run note is `questions`, no human input since) and keeps
  `approved_landing` (UI label "approved, awaiting Mac"). `research_on` is `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`.
- SPA summary adds `awaitingAnswer`; `GET /api/board/trash` → `{items: [{id, title, deletedAt, purgeAfter}]}`.
  Decision verbs `delete` (no reason, no hash) and `restore` (card in trash) go through the broker.
