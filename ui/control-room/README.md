# Control Room frontend (`ui/control-room/`)

The Praetorium Control Room screen — the Figma prototype, wired to the read-model API served by
`bin/control_room_api.py` (T5.3e). `control-room.service` serves the **committed build** under
`bin/control_room_ui/app/` at `/app/`; `/` redirects there. The server-rendered pages
(`/exceptions`, `/portfolio`, `/benefit`, `/workflows/<id>`, `/runs/<id>`) stay as the no-JS
fallback and are unchanged.

- Stack: React 19, Vite 8, Tailwind 4 (`@theme inline` tokens in `src/index.css`), recharts 3,
  zod 4, vitest 5 + Testing Library. Fonts are self-hosted through `@fontsource` so the page
  loads under the API's `default-src 'self'` CSP with no third-party request.
- Design source: https://www.figma.com/make/W8HXm1FY9cSiuQj53neasO/Review-attachment, spec at
  `docs/spec.md`. The prototype's demo data (`src/data.ts`, per-page `MOCK_*`) is gone; every
  number on the screen comes from `/api/v1/*`.

## Layout

| Path | Owns |
|------|------|
| `src/api/schemas/` | one zod schema per endpoint, lenient on unknown keys; enumerations parse as strings |
| `src/api/client.ts` | `getJson` / `getText` / `postControl` / `postProposal`; `X-Control-Room: 1` on both POST seams; `ApiError {status, body}` |
| `src/api/useResource.ts` | `loading \| ready \| error` per resource, refresh, auto-refresh tick |
| `src/model/` | mappers from API shapes to view types; every vocabulary has an `unknown` fallback; `Measurement<T>` is `measured \| unavailable \| unknown` |
| `src/router/` | seven routes under `/app/`; unknown paths land on Overview flagged |
| `src/shell/` | `App` (sidebar, header, health footer), the refresh context, page-resource hooks |
| `src/pages/` | Overview, Workflows, WorkflowDetail, RunDetail, Incidents, Usage, Activity |
| `src/components/` | badges, measurement cells, links, panels, the data-status strip |
| `src/components/dialogs/` | the control and proposal dialogs (T5.3a / T5.3b seams) |

Rules the code keeps: `unavailable` is a value, never 0; an unknown API value renders as
`unknown`, never crashes; the fleet's timers are never enabled or started from here — every
control path is the API's own preview/apply/refuse contract, rendered.

## Develop

```
cd ui/control-room
npm ci
npm run dev          # Vite on :5173; set VITE_API_PROXY=http://<praetorium-tailscale>:8787 to proxy /api
npm test             # vitest, jsdom, fixtures mirror tests/fixtures/control-room
npm run typecheck
```

## Build and commit

The build is a committed artifact with fixed names (`index.html`, `assets/app.js`,
`assets/app.css`, `assets/*.woff2`) plus `BUILD.json` carrying a sha256 over the tracked
source tree. Never run `vite build` by hand into `bin/`; use the wrapper, which refuses
Node < 22, runs typecheck + tests + build, and writes the stamp:

```
bin/control_room_build_ui.sh        # from the repo root
```

`tests/test_control_room_spa.sh` fails the gate when the committed build's stamp no longer
matches the source (edit `src/`, forget to rebuild) and checks the shell's hygiene under the
CSP. CI installs Node 22 and `npm ci` here before the gate, so a stale build is red there too.
Runbook § Control Room, "Frontend build".
