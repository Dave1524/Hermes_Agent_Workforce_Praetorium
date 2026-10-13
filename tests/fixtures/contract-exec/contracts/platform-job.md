# Contract: platform-job

Fixture for tests/test_receipt_finish.py. A deterministic platform timer: no attempt log and
no `run` checks, so its receipt's evidence is systemd's verdict alone. Its two `sweep` checks
are what the finish step leaves `not_applicable: vantage` for the sweep to decide. Not under
design/contracts/, so the validator never grades it.

## Identity

| | |
|---|---|
| Unit | `platform-job.service` / `.timer` |
| Owner | **fixture** |
| Surface | platform — a fixture |

## Trigger

never — a fixture.

## Inputs

none

## Outputs

- **State change:** whatever systemd says the run did.
- **Beneficiary:** tests/test_receipt_finish.py.
- **Next actor:** the suite.
- **Next action:** read the receipt.
- **Benefit hypothesis:** a fix is visible when the run that proves it ends.
- **Benefit signal:** `Unknown`.

## Decline conditions

none

## Side effects

none

## Acceptance checks

1. **The failure was alerted** — decidable only after the unit has failed, so from outside.
   The suite makes it fail by writing `$HOME/alert-missing`.

   ```check id=failure-alerted when=sweep
   [ ! -f "$HOME/alert-missing" ] || { echo "no alert for the run started @$AGENT_RUN_STARTED_AT"; exit 1; }
   ```

2. **The timer is loaded** — always green here.

   ```check id=timer-is-loaded when=sweep
   [ -n "$SYSTEMCTL" ]
   ```

## Known failure modes

none
