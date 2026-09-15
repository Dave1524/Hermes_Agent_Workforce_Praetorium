# alpha — workflow contract (fixture)

## Identity

| field | value |
|---|---|
| id | `alpha` |
| owner | claudius |
| retry | idempotent — re-running rewrites the same dated proposal |

## Trigger

`OnCalendar=Sun 09:00`, `RandomizedDelaySec=5min`. Recurring; no expiry.

## Artifact

One dated proposal under `_inbox/agents/`.
