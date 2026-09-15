# gamma — workflow contract (fixture)

## Identity

| field | value |
|---|---|
| id | `gamma` |
| owner | claudius |
| retry | idempotent |

## Trigger

Two timers: `OnCalendar=Tue 03:00` (gamma) and `OnCalendar=Sat 22:00` (gamma-dispatch).

## Artifact

One distillation per source.
