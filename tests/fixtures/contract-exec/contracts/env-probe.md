# Contract: env-probe

Fixture for tests/test_contract_exec.py. Not under design/contracts/, so the validator never
grades it — which is the point: check 1 reads a variable the schema does not declare, to prove
the executor withholds it.

## Identity

| | |
|---|---|
| Unit | `env-probe.service` / `.timer` |
| Owner | **fixture** |
| Surface | fixture |

## Trigger

never — a fixture.

## Inputs

none

## Outputs

- **Artifact:** none; the receipt is the artifact.
- **Beneficiary:** tests/test_contract_exec.py.
- **Next actor:** the suite.
- **Next action:** compare the environment against the schema list.
- **Benefit hypothesis:** a variable that leaks from the parent shows up red.
- **Benefit signal:** `Unknown`.

## Decline conditions

none

## Side effects

none

## Acceptance checks

1. **The parent's variables do not reach the block.**

   ```check id=secret-probe
   [ -z "${SECRET_PROBE:-}" ]
   ```

2. **The block sees exactly the schema's environment.** Prints it; the suite reads the keys.

   ```check id=env-dump
   env
   ```

3. **A sweep-only check**, so a run-vantage receipt carries one `not_applicable` by vantage.

   ```check id=sweep-only when=sweep
   [ -n "$SYSTEMCTL" ]
   ```

## Known failure modes

none
