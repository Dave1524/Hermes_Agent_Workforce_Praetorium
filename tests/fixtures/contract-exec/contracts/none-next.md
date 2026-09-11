# Contract: none-next

Fixture for tests/test_contract_exec.py: an artifact that terminates. Next actor and next
action are `none`, which the receipt must carry as null rather than as the word.

## Identity

| | |
|---|---|
| Unit | `none-next.service` / `.timer` |
| Owner | **fixture** |
| Surface | fixture |

## Trigger

never — a fixture.

## Inputs

none

## Outputs

- **Artifact:** the attempt log itself.
- **Beneficiary:** tests/test_contract_exec.py.
- **Next actor:** none
- **Next action:** none
- **Benefit hypothesis:** a terminating artifact is recorded as one.
- **Benefit signal:** `Unknown`.

## Decline conditions

none

## Side effects

none

## Acceptance checks

1. **The attempt log exists.**

   ```check id=attempt-log-exists
   [ -f "$AGENT_ATTEMPT_LOG" ]
   ```

## Known failure modes

none
