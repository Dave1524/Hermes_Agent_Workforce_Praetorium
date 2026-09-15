# refresh — workflow contract (fixture)

## Identity

| field | value |
|---|---|
| id | `refresh` |
| owner | trajan |
| retry | idempotent |

## Trigger

Monotonic: fires every 15 minutes after the previous activation. No calendar.

## Artifact

A refreshed index.
