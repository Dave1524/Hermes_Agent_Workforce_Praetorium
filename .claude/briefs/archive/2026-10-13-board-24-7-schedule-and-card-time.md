# Brief: Board runs 24/7 and cards carry a time
**Date:** 2026-10-13   **Verify:** `bash bin/verify.sh` (from repo root); UI: `cd ui/control-room && npx tsc -p tsconfig.json --noEmit && npx vitest run`; `bash tests/test_control_room_spa.sh` after `bin/control_room_build_ui.sh`. Extra-gates/smoke: none declared in the repo CLAUDE.md.

## Acceptance criteria
1. A card's `research_on` accepts `YYYY-MM-DD` (as today, means 00:00) or `YYYY-MM-DDTHH:MM`, read as box-local time (Europe/Amsterdam). A bad time (`25:00`, `T9:5`, a time with no date) is refused with the same `BoardError` style as a bad date.
2. A Todo card is `scheduled` until `now >= research_on` to the minute, not to the day. The pick passes over it until then. A Backlog or any other column is never `scheduled` (unchanged).
3. `research_on` after `deadline` is still refused (compare on the date part; a deadline stays a date).
4. The popup edits it with a date-and-time control and shows it as `2026-10-14 06:30`; a date-only value shows as the date. Existing cards with date-only values behave as before.
5. A new unit pair `board-research.{service,timer}` runs the research pick hourly, 24/7 (`*-*-* *:37`, RandomizedDelaySec=3min, Persistent=false) with a model-free quiet tick: no Todo card ready means a receipted `skipped`, no model starts. It reuses the standing-research runner with `AGENT_BOARD_PICK="--owner claudius --kind research --column todo"` and `AGENT_BOARD_REQUIRED=1`.
6. `research-brief.timer` becomes hourly 24/7 (`*-*-* *:07`), same model-free pre-flight.
7. Both workflows appear in the Control Room with pause, resume, run-now and `Change schedule…` (they must be in the broker allowlist: timer + service under `systemd/`, a manifest entry, a `config/fleet-units.tsv` row, a contract).
8. `agent-proposal` (the 03:30 weekday standing research) is unchanged and keeps its Todo pick; the pick is idempotent per run id and the column is derived, so a card cannot be worked twice.

## Files to modify
- `bin/board.py` — `check_date`-style `check_research_on` (date or datetime), `check_dates_agree` compares the date part, `derive()` scheduled compares to a local datetime built with `now.tzinfo`, `--research-on` help text, `render_card_md` prints the time when present.
- `bin/control_room_board_writes.py` — accept the datetime string for `research_on` on create and edit (strings already admitted; pin the length/shape).
- `ui/control-room/src/components/card/CardSidePanel.tsx` — `research_on` uses `datetime-local`; `deadline` stays `date`; hint text becomes "Not before this date and time".
- `ui/control-room/src/model/cardDraft.ts` — draft round-trip of `YYYY-MM-DDTHH:MM`.
- `ui/control-room/src/model/card.ts` — a `formatResearchOn` display helper (date-only stays the date).
- `systemd/research-brief.timer` — `OnCalendar=*-*-* *:07:00`; comment header updated.
- `design/agents/claudius.toml` — `research-brief` trigger string "hourly, every day (+3min jitter)"; new `[[workflows]]` entry `board-research`.
- `design/contracts/research-brief.md` — `## Trigger` tokens follow the timer.
- `config/fleet-units.tsv` — row `board-research	system	standing	claudius	timer`.
- `bin/buzz_producers.tsv`, `docs/runbook.md` (Job wiring table, a "Card time and the 24/7 board" paragraph, hand-install steps), `design/fleet-suites.toml` (anchors for the new tests), and the three files that pin the `[[workflows]]` count (memory `retire-plan-count-literal-gap`: ADDING one is three hand-edits; find them with `grep -rn` for the current literal).
- `bin/control_room_ui/app/` — rebuilt by `bin/control_room_build_ui.sh`.

## Files to create
- `systemd/board-research.service` — cloned from `research-brief.service`; same `ConditionPathExists=/var/lib/control-room-board`; `AGENT_JOB_OVERRIDES=.../board_research.env`; `TimeoutStartSec` sized by `bin/propose_budget.py` (standing research is longer than a brief; read the budget test before choosing).
- `systemd/board-research.timer` — `OnCalendar=*-*-* *:37:00`.
- `profiles/board_research.env.example` — `AGENT_PROFILE`, `AGENT_OWNER=claudius`, `AGENT_TASK_SLUG=board-research`, the pick above, `AGENT_BOARD_REQUIRED=1`, runner and verify as `standing_research.env.example` names them.
- `design/contracts/board-research.md` — eight fixed sections; Identity retry row set so the allowlist renders.
- `tests/test_board_research_smoke.sh` — wiring smoke cloned from `tests/test_research_brief_smoke.sh`.
- Tests added to existing files, not new ones: `tests/test_board.py` (below), `tests/test_control_room_board_writes.py`, `ui/control-room/src/components/dialogs/CardDialogEdit.test.tsx`, a `cardDraft` model test.

## Order of work
1. Test: `tests/test_board.py` cases — date-only unchanged; datetime accepted; `T25:00` refused; time without a date refused; Todo card with `research_on` an hour ahead is `scheduled`, one minute past is not; Backlog with a future time is not scheduled; `research_on` later than `deadline` refused. Run, see red.
2. Change `bin/board.py` until green.
3. Test then change `bin/control_room_board_writes.py` (create and edit carry the datetime; malformed refused with 400).
4. UI: test the draft round trip and the dialog (edit sets a datetime, display), then `cardDraft.ts`, `card.ts`, `CardSidePanel.tsx`. `npx tsc` and `npx vitest run`.
5. Timers and units: copy `research-brief.*` to `board-research.*`, edit; update `research-brief.timer`; env example; contract; manifest entry; `fleet-units.tsv`; producers; the three count literals. Run `tests/test_workflow_*`, `test_control_room_views.sh`, `test_propose_budget.sh`, `test_instruction_size.sh` red-to-green as the new rows land.
6. `tests/test_board_research_smoke.sh`: a Todo card past its time is picked; a Todo card ahead of its time is a receipted skip; empty board is a receipted skip.
7. `bin/control_room_build_ui.sh`, then `bash tests/test_control_room_spa.sh`.
8. Runbook and `design/fleet-suites.toml` anchors; `bash bin/verify.sh`, the full run detached (about ten minutes). Report deploy drift as expected (the new units are not installed).

## Test plan
- Board derivation unit tests (step 1) are the gate for the time semantics; boundaries to the minute, both sides.
- Seam test: the same strings through `control_room_board_writes`; refusal bodies are 400 with the board message.
- UI: round trip and display for date-only and datetime values; vitest count goes up, none removed.
- Allowlist: `control_broker_allowlist.py check` includes `board-research` and `research-brief` (the views test renders them as pausable).
- Smoke for the new unit with the same fake-claude harness as `test_research_brief_smoke.sh`.

## Out of scope / do not touch
- The 03:30 `agent-proposal` timer, its profile and its Todo pick.
- The brief run's gate: a Backlog card is briefed whatever its research time (see Notes); do not make the time hold the brief.
- Any change to the broker or the Control Room backend beyond the allowlist picking up the new unit. The Control Room already has pause, resume, run-now and the schedule PR.
- Installing or enabling units: Dave hand-installs after merge.
- Sub-hour cadence, and time zones other than the box's.

## Risks
- Hourly 24/7 turns every quiet tick into a receipt row (two units, 48 a day). Tell: the receipts directory and `receipt_sweep` runtime grow; the Control Room shows many `skipped`. Response: lengthen the cadence from the screen's `Change schedule…`; if sweep cost is visible, stop and tell Dave before merging.
- A card due at 03:37 runs a full Opus research at night while no human is awake; Dave approves only afterwards, so cost is incurred before review. Tell: `cost.log` rows at odd hours. Response: Dave sets the time; the brief approval is still the human gate before any research run.
- Local time across the DST change (last Sunday of October): `derive()` uses an aware local `now`; a time inside the repeated or skipped hour could fire an hour early or late. Tell: a card picked at the wrong hour twice a year. Response: accept; do not add tz libraries.
- Two timers pick Todo (03:30 standing job and the hourly one). The pick is idempotent and the column derived, so double-work is prevented only if both read the same board root. Tell: two `picked` events for one card. Response: stop; remove the Todo pick from `standing_research.env`.
- The schedule screen produces a PR; the unit files still reach `/etc/systemd/system` by hand. Dave may expect a merged schedule change to apply. Tell: drift check red after merge. Response: the runbook step below; not solved here.

## Notes / preconditions
- Correction recorded: `board.py` derive sets `scheduled` only when the column is Todo (`board.py:373`), so a Backlog card with a future `research_on` is not held back from the brief run. The card created on 2026-10-12 was not briefed only because `research-brief.timer` is disabled and not installed.
- `research_on` today is a date; the whole stack already treats it as an opaque string except `check_date` and `derive`, so widening it to a datetime string avoids a second field.
- The Control Room already offers: pause = `systemctl disable --now <unit>.timer`, resume = `enable --now` (catch-up starts the service immediately, `control_broker.py:473`), run-now = start the service, and `Change schedule…` as a `control-room/*` PR that rewrites the timer, manifest trigger and contract Trigger tokens (`bin/workflow_pr_schedule.py`). All need the unit installed; the broker does not install units, and `enable` on an uninstalled timer fails (inferred from `control_broker.py`, not tested live).
- `research-brief` is Mon..Fri 08-18 in the manifest and timer today; `agent-proposal` is Mon..Fri 03:30.
- Board root `/var/lib/control-room-board`; the seam refuses writes from the box itself (`peer_denied`), so card edits in UI tests are mocked.

## Land-time steps (after merge; Dave runs the sudo lines)
```
cd ~/dev/agent-workforce && git checkout main && git pull && bin/deploy
sudo cp systemd/research-brief.service systemd/research-brief.timer systemd/board-research.service systemd/board-research.timer /etc/systemd/system/
sudo python3 bin/control_broker_allowlist.py render | sudo tee /etc/control-room/allowlist.json >/dev/null
sudo systemctl daemon-reload
sudo systemctl restart control-room.service
```
Then create `~/.config/agent-workforce/board_research.env` and `research_brief.env` from the two `profiles/*.env.example` files (mode 600, outside git), and enable from the screen: workflow page, Resume, for `research-brief` and `board-research`. First check after: `systemctl list-timers 'research-brief*' 'board-research*'`.
