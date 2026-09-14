# Control Room prototype (Figma Make export)

Design reference for the Praetorium Control Room front end. **Demo data only** — nothing here
reads the box, and nothing here is deployed.

- Source: https://www.figma.com/make/W8HXm1FY9cSiuQj53neasO/Review-attachment
  (imported 2026-09-14 via the Figma MCP `file://figma/make/source/...` resources)
- Spec the prototype was generated from: `src/imports/pasted_text/praetorium-control-room.md`
- Stack: React 19, Vite 8, Tailwind 4 (`@theme inline` tokens in `src/index.css`), recharts 3,
  TypeScript. All screen data is hardcoded in `src/data.ts` and in per-page `MOCK_*` constants.

## What changed from the Make export

- `vite.config.ts` — replaced Figma's build config with a plain react + tailwind config; `@` alias kept.
- `index.html` — Figma template slots removed, title set.
- `src/assets/reference.png` — dropped: not a PNG (the file held the prompt text, misnamed).
- `src/imports/pasted_text/praetorium-control-room.md` — first character restored (`reate` -> `Create`).
- Unreferenced hash-named images under `file://figma/make/image/...` were not imported.
- Everything under `src/` is otherwise verbatim.

## Run locally

```
cd ui/control-room-prototype
npm install
npm run dev
```

Needs Node. The `verify` gate does not touch `ui/`, and `bin/deploy` does not ship it.

## Relation to the landed backend (T5.3)

`control-room.service` serves the real data from `bin/control_room_api.py` on the Tailscale
address, port 8787: server-rendered pages at `/exceptions`, `/portfolio`, `/benefit`,
`/workflows/<id>`, `/runs/<id>`, and a JSON API under `/api/v1/`. The prototype's IA is
different (Overview / Workflows / Incidents / Usage / Activity sidebar) and its dialogs
belong to later briefs. Nothing in it has to be reconciled now; the mapping when it is wired:

| Prototype screen / data              | Backend today                                      | Brief |
|--------------------------------------|----------------------------------------------------|-------|
| Overview cards, Needs attention      | `GET /api/v1/overview`, `GET /api/v1/exceptions`   | T5.3 |
| Workflows table, trigger expander    | `GET /api/v1/workflows`, `/workflows/<id>`         | T5.3 |
| Workflow detail, Recent runs         | `GET /api/v1/workflows/<id>/runs`, `/runs/<id>`    | T5.3 |
| Benefit evidence, reliability chart  | `GET /api/v1/benefit`                              | T5.3 |
| Usage table and chart                | `GET /api/v1/usage` (`unavailable` until T5.2)     | T5.2 |
| Incidents tabs                       | `GET /api/v1/incidents` (read); ack/Buzz rules     | T5.3c |
| Activity log, Marcus -> Trajan timeline | `GET /api/v1/activity`; handoff detail          | T5.3d |
| Pause / Resume / Run now / Retry / Stop dialogs | `POST /api/v1/control/actions` (501 stub, needs `X-Control-Room: 1`) | T5.3a |
| Change schedule / Retire PR dialogs  | none                                               | T5.3b |

Shape differences to keep in mind when swapping `data.ts` for fetches: the API's `usage` and
`cost` are `measured | unavailable` objects with null fields, never 0 — the prototype's
`available: false` rows are the same idea; the API's terminal outcomes are `artifact | decline
| failed | skipped`, the prototype's are `success | incomplete | failed | running`.

## Wiring plan (later brief)

1. Replace `src/data.ts` imports with fetches against `/api/v1/*` (same origin).
2. `vite build` to static assets, copied under `bin/control_room_ui/` so `bin/deploy` ships
   them and the existing `default-src 'self'` CSP holds. The Google Fonts `@import` in
   `src/index.css` must go (blocked by CSP) — self-host or fall back to the system stack.
3. Keep the SSR pages as the no-JS fallback, or retire them once the SPA is proven.

No Node toolchain lands in the deployed tree; the build output does.
