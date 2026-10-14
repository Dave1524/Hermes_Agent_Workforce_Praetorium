# Contract: board-reactor

Written 2026-10-13 with `systemd/board-reactor.service`, `bin/board_reactor.py`,
`bin/board_source.py`, `bin/board_plan.py` and `.claude/briefs/current.md` (event-driven board
reactor). Read for this contract: those files, `systemd/board-{brief,work}@.service`,
`config/polkit/50-board-reactor.rules` and `bin/board.py`.

**A control loop, not a scheduler.** Each pass observes the board (`board.py collect`, deleted
cards and the trash included) and the run units systemd reports active, plans from that state
alone (`board_plan.plan`, pure) and applies one action at a time. inotify on the board, each
card and the two run templates' receipt directories is only a wake-up: a lost event costs at
most the next wake, the reconcile timer's five minutes in the worst case.

## Identity

| | |
|---|---|
| Unit | `board-reactor.service` (no timer; `Type=notify`, always on) |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | platform — deterministic python, no model; starts the model runs it governs |
| Runner | `bin/board_reactor.py` (exit 0 on SIGTERM, 2 on a permanent error, which `Restart=on-failure` retries with backoff) |
| Supervision | `WatchdogSec=60`, pinged every third of it; `Restart=on-failure`, `RestartSec=5` stepping to 300 s; `StartLimitBurst=10` per hour |
| Alerted | yes — `OnFailure=agent-alert@%n.service`, once the start limit is spent |
| Remediation owner | claudius |
| Retirement condition | none while the board runs work: no card starts any other way |
| Contract version | 1 (2026-10-13) |
| Retry | idempotent: every pass re-derives its plan from the ledger and systemd, and `systemctl start` of an active unit is a no-op, so a restart repeats nothing that already happened |

## Trigger

Always on (`WantedBy=multi-user.target`). Woken by inotify on `$BOARD_ROOT`, `cards/`, each card
directory, the trash, the decisions stream and the receipt directories of `board-brief` and
`board-work`; otherwise by its own wake time (a card's cooldown or backoff ending, a scheduled
card's due time, a free slot re-check after 30 s, midnight when capped) and a 300 s resync.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| the card ledger under `$BOARD_ROOT` (`board.collect`, `include_deleted=True`) | as of the pass | an unreadable ledger raises; the pass fails `transient` and backs off |
| `systemctl list-units 'board-brief@*' 'board-work@*'` | as of the pass | a refusal is classed: polkit or a missing unit `permanent`, anything else `transient` |
| `$BOARD_ROOT/reactor/state.json` — per-card starts, backoff, the day's run count | written atomically by the previous pass | absent is an empty memory; the cap counts from zero |
| `/var/lib/control-room/receipts/board-reactor/*.json` — the broker's start/stop receipts | read by the reconcile only | absent means not paused |

## Outputs

- **Artifact** — `systemctl start --no-block board-brief@<card>.service` or
  `board-work@<card>.service`; `held` ledger events (actor `reactor`, reason `poison-attempts` or
  `poison-start`); trash, restore and purge of deleted cards; and a vantage-`run` receipt (`bin/reactor_receipt.py`) under
  `~/agent-workforce/var/workflow-receipts/board-reactor/` on every **health flip** only (`ok`,
  `transient`, `capped`, `permanent`, with a reason code), `failed` for `capped` and `permanent`.
- **Log** — one journal line per applied action and per flip; `STATUS=` carries the last pass.
- **Beneficiary:** Dave — a card he moves is worked within seconds instead of the next hourly tick.
- **Next actor:** the started run (`board-brief@` / `board-work@`), which receipts itself.
- **Next action:** none from Dave unless a card is held or health is not `ok`; both show in the
  Control Room.
- **Benefit hypothesis:** edge-triggered starts cut a card's wait from up to an hour (and a
  weekend) to seconds, with no more runs than before.
- **Benefit signal:** the gap between a card's moving event and its `picked` event, countable from
  the ledger; target ≤ 5 s on the edge, ≤ 5 min on reconcile.

## Decline conditions

none. A card that is quarantined, cooling down, over the cap or waiting for a slot is a planned
non-start, not a decline; each is visible in the pass's status and in the card's view.

## Side effects

- At most `BOARD_REACTOR_MAX_RUNS` (2) run units active at once; at most
  `BOARD_REACTOR_DAILY_CAP` (24) starts per box-local day.
- `$BOARD_ROOT/reactor/{lock,state.json,heartbeat}`; one flock per pass, shared with the reconcile.
- Deleted cards stopped, then moved to `$BOARD_ROOT/trash/`; purged 30 days later.

## Acceptance checks

An always-on unit has no run for the contract executor to decide a check from, so these are
decided by the suites and by the reconcile, not by `bin/contract_exec.py`.

1. **An edge starts a run within 5 s, and the watchdog is pinged at under half its period.**
   `tests/test_board_reactor.py` (Daemon): the real process against a fake `NOTIFY_SOCKET`.
2. **The plan is a function of state.** `tests/test_board_plan.py`: triggers, the budget, the
   cooldown, both quarantines, delete, restore and purge, from fixed views and a fixed clock.
3. **Every flip, and only a flip, is receipted, in the shape `workflow_receipt` validates.**
   `tests/test_board_reactor.py` (Pass, ErrorClasses, Cap).
4. **A dead reactor is red within five minutes; a paused one is not.** The reconcile's
   `daemon-dead` receipt, `tests/test_board_reactor.py` (Once).
5. **polkit grants dave start and stop on the two templates and nothing else.**
   `tests/test_board_polkit.py`.

## Known failure modes

- **inotify watch limit.** `ENOSPC` on a watch exits 2 with `permanent inotify-limit`; raise
  `fs.inotify.max_user_watches`. Signal: the flip receipt's reason.
- **polkit rule not installed.** Every start fails `permanent polkit-denied`; the rule is a hand
  install (runbook § Board reactor). Signal: the reason code.
- **A card that never reaches a pick.** Three starts with no `picked` after them hold the card
  `poison-start`; three void runs hold it `poison-attempts`. Signal: the card's `held` event.
- **A lost inotify event.** Nothing breaks; the reconcile's pass five minutes later applies it.
