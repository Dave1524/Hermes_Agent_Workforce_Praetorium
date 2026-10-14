# Brief: B9 broker decisions (note §3.7, §3.8, §7 decisions 10 and 12)

Scope: B9 only. B10 is Mac-side in the vault repo and waits on the watcher fail-open fix; not shipped here.

## What
1. `bin/control_broker.py`: seven Dave-only board verbs (brief_approved, brief_returned, approved,
   changes_requested, rejected, blocked, unblocked) as allowlisted broker requests
   (`board_verb`). Each appends one signed line to `<board dir>/decisions.jsonl`
   (default `/var/lib/control-room/receipts/board`, world-readable, root-written). Signature:
   `ssh-keygen -Y sign -n board-decision` with `/etc/control-room/board_signing_key` over the
   canonical JSON of the record minus `sig`. `approved` carries the page text and must hash to
   `page_hash`; the text stays in the signed record. Refusals write nothing. The broker never runs board.py.
2. `bin/control_broker_allowlist.py`: renders a `board.verbs` table; the broker refuses a verb not in it.
3. `bin/board_decision_sig.py`: reference verifier (canonical bytes, `verify`), pinned by tests; the
   Mac pass (B10) re-implements it from the runbook.
4. Seam (`control_room_board_writes.py`): the eight popup verbs (approve_brief, return_brief, approve,
   request_changes, reject, withdraw, block, unblock) map to the seven; checked against the card's
   `moves`, the brief hash / page hash the popup rendered (stale = 409), reasons required, then sent
   to the broker. withdraw = rejected outside In Review. No broker socket = 503.
5. Popup: footer buttons live, reason box, "Save and approve" (brief) and "Save and unblock" (deadline).
   Rebuild the committed SPA.
6. Runbook, CLAUDE.md-free; hand-install commands for the root files and the signing key (never `bin/deploy`).

## Acceptance
- `tests/test_control_broker.py` seven verbs, signature verifies, tamper fails, refusals write nothing.
- `tests/test_board.py::forged-decision-ignored` stays green; a broker-written line is read by `derive`.
- Seam cases in `tests/test_control_room_board_writes.py`; `CardDialog*.test.tsx` decision cases.
- `bash bin/verify.sh` green except deploy drift for the changed root paths.

## Test plan
Fixture keys from `ssh-keygen` in temp dirs. Synthetic cards only.
