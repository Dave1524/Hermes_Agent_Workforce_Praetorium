# Praetorium Control Room — read-only backend/API vertical slice

Date: 2026-09-11

## Why this slice

The published Figma prototype at `https://sand-boil-02043797.figma.site` is the visual and
interaction reference for T5.3. It currently renders hard-coded demo data and simulated
actions. This slice gives that frontend a production-shaped, read-only API over the sources
Praetorium already owns without pretending that T5.1/T5.2 receipt wiring has landed.

The source hierarchy stays:

1. `design/agents/*.toml` for workflow identity, ownership and declared lifecycle;
2. `design/contracts/*.md` for beneficiary, next actor/action and benefit semantics;
3. systemd for live timer/service state;
4. `~/agent-workforce/var/workflow-receipts/` for structured run truth once T5.1/T5.2 emit it.

Missing contracts, systemd access or receipt telemetry render as explicit `unknown` /
`unavailable` states. They never become healthy status, zero tokens or zero cost.

## Scope

- A dependency-light Python read model and HTTP server under `bin/`.
- Versioned JSON endpoints for health, overview, workflows, workflow detail, runs,
  incidents, usage and activity.
- One logical workflow in the response when multiple technical triggers share one contract
  (the live `augustus-content` / `content-change-dispatch` case).
- Read-only enforcement: non-GET/HEAD methods return `405`; T5.3a's root-owned control broker
  remains a separate trust boundary.
- Atomic, bounded receipt reads. Malformed receipts become named data-quality incidents and
  never crash or disappear from the API.
- CORS disabled by default. The production frontend is expected to be same-origin.
- Unit and API tests use fixture roots and a fake systemd reader; they never mutate live
  timers or read the deny-listed trees.

## Explicitly not complete in this slice

- T5.1 contract execution and the canonical receipt writer.
- T5.2 wiring across all 30 logical standing workflows.
- T5.3a live controls, T5.3b PR creation, T5.3c Buzz incidents or T5.3d handoff capture.
- Importing/rebuilding the Figma frontend.
- A system unit. The API can be smoke-run on loopback; durable private hosting is installed
  with the frontend once its same-origin service boundary is selected.

## API contract

- `GET /api/v1/health`
- `GET /api/v1/overview`
- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_id}`
- `GET /api/v1/workflows/{workflow_id}/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/incidents`
- `GET /api/v1/usage`
- `GET /api/v1/activity`

All collection responses carry `generated_at`, `data_status` and `items`. `data_status`
names unavailable sources so the frontend can show an honest degraded state.

## Gate

- Fixture manifests reconcile technical entries to logical workflows deterministically.
- A two-trigger shared contract appears once with both triggers.
- Missing/malformed receipts and inaccessible systemd each stay visible by name.
- Unknown token/cost fields remain `null` with `status = "unavailable"`.
- Path traversal, unknown routes and write methods fail closed.
- Loopback smoke test exercises the HTTP routes.
- `bin/deploy`, then `bash bin/verify.sh`.
