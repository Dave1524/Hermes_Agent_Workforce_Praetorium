# Board: event-driven refactor — requirements gathered from Dave (2026-10-13)

Input to the `/plan-feature` run for the event-driven Kanban. Not the brief. The production-first
rule applies: research first, forks under `## Decisions for Dave`, nothing ranked by cost or speed.
Supersedes `board-24-7-schedule-and-card-time.md` (hourly timers; the cheap route).

## What Dave asked for
1. **A card acts when it is created or approved**, not at the next timer tick. Scope: the Kanban
   and its card scheduling only, not the cron jobs.
2. **A time on the card**, not only a date (`research_on` as date or datetime, box-local).
3. **Runs 24/7**, no weekday or office-hour window.
4. **The reactor supervises itself.** Restart on failure with backoff, hang detection, an
   independent second path (reconcile timer, same pure function), and error classes with reason
   codes: transient (retry), poison card (quarantine that card), permanent (stop and alert).
5. **Merge `idea` into `brief`.** The card is a title and a brief. The id is derived from the title.
6. **Delete means delete.** Today, deleting a card requires a reason and the card lands in
   Done as `withdrawn`. It is not done work; it should leave the board, with no reason prompt.
   See D3 below.
7. **Production quality, not the quickest version.** Do the research first.

## Facts the plan must respect (verified 2026-10-13)
- `board.py` derives every column from the ledger. `scheduled` applies only to Todo cards
  (`board.py:373`); a Backlog card is briefed regardless of its research date.
- `research-brief.timer` is installed (11 Oct) but disabled; nothing picks up Backlog cards today.
- `board.py land` and `sweep` have no automatic caller that I could find (grep of `bin`,
  `systemd`, `config`, `profiles`, the contracts, the runbook). Confirm with a synthetic card.
- The first live decision was taken 2026-10-13 13:10Z (a rejection); its signature verifies.
  The Mac side (watcher board pass, B10) has not seen a real approval yet.
- The seam refuses writes from the box itself (`peer_denied`); the card was created with
  `board.py` as `dave` by explicit request.
- Rejecting a card outside In Review produces `Done / withdrawn`; the seam requires a reason for
  every Dave decision verb (`board_write` seam, B9).
- PR #106 constraints: every standing row needs exactly one receipt producer
  (`tests/test_receipt_coverage.py`, a `board-reactor` service has none today); every platform
  timer except the sweep ends on `-receipt_finish.py %N`, so a reconcile timer running
  `board.py react --once` must too; record state flips, not every tick; a flapping unit sends an
  `[incident]`/`[recovered]` pair per flip and the debounce follow-up is not built, so reactor
  restarts could page in a storm. Reason codes can ride on the finish step's evidence (exit status).

## Decisions for Dave (open; to be carried into the brief)
- **D1 Burst:** 20 cards at once: one run at a time (queue) or parallel?
- **D2 Quiet hours:** may an unattended run start at 03:00, or hold 23:00-07:00 unless the card
  has an explicit time?
- **D3 Delete:** (a) hard delete: remove the card from the ledger; the signed decision stream
  keeps its history, so the audit trail is not lost. (b) a `deleted` state hidden from every column,
  card kept on disk for recovery. (c) keep rejection for work in review, add a separate Delete
  for anything else. Research the audit and recovery trade-offs first; do not default to (a)
  because it is simplest.
- **D4 Daily cap** on model runs, and **D5 loop protection** (cooldown plus the two-strike block).
- **D6 Mac asleep:** merge on wake, or notify and wait?
- **D7 Brief authoring:** with idea merged into brief, does a rough thought typed into Brief get
  restructured by the agent (Dave's text kept as version 1), or does the agent ask questions first?
- **D8 Scope later:** Kanban only, built generic enough that inbox and approvals can join the
  reactor, or Kanban only with no extension point.

## Research to do first
Event-driven job dispatch and reconciliation patterns (level- plus edge-triggered control loops,
outbox and idempotent consumers, supervised workers with watchdogs and backoff); how queue-driven
agent systems handle bursts, quiet hours, and poison messages; delete versus soft-delete in
append-only, signed decision logs. Cite context7 and web sources in `## Design research`.
