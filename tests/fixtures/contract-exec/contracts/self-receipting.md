# Contract: self-receipting

Fixture for tests/test_receipt_sweep.py (T7.3). A unit that receipts its own run at vantage
`run` — the agent_propose.sh shape — whose contract also carries `when=sweep` checks, so the
sweep's second look has something to decide. Not under design/contracts/, so the validator
never grades it.

## Identity

| | |
|---|---|
| Unit | `self-receipting.service` / `.timer` |
| Owner | **fixture** |
| Surface | fixture |

## Trigger

never — a fixture.

## Inputs

none

## Outputs

- **Artifact:** whatever the run says it produced.
- **Beneficiary:** tests/test_receipt_sweep.py.
- **Next actor:** the suite.
- **Next action:** read the amended receipt.
- **Benefit hypothesis:** a sweep check the run could not decide is decided by the sweep.
- **Benefit signal:** `Unknown`.

## Decline conditions

none

## Side effects

none

## Acceptance checks

1. **The attempt log exists** — decided by the run.

   ```check id=attempt-log-exists
   [ -f "$AGENT_ATTEMPT_LOG" ]
   ```

2. **Delivery landed after the run** — decidable only from outside, after ExecStartPost.
   The suite makes it fail by writing `$HOME/delivery-failed`.

   ```check id=delivered-after-the-run when=sweep
   [ ! -f "$HOME/delivery-failed" ] || { echo "delivery failed for the run started @$AGENT_RUN_STARTED_AT"; exit 1; }
   echo "delivered for the run started @$AGENT_RUN_STARTED_AT"
   ```

3. **The timer is loaded** — the other sweep check, always green here.

   ```check id=timer-is-loaded when=sweep
   [ -n "$SYSTEMCTL" ]
   ```

## Known failure modes

none
