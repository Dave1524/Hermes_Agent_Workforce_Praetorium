# Brief: NUC-21/Brave — Fix Brave MCP tool registration (live verification fails)
**Date:** 2026-07-08   **Verify:** `bash bin/verify.sh` + a live search that returns results

> **Where this runs:** live MCP wiring is outside git
> (`~/.hermes/profiles/research_analyst/config.yaml`, `~/.hermes/.env`); run `/implement` on the box and
> iterate against real `hermes -p research_analyst` runs. Any in-repo change (status line/test) is gated by
> `bin/verify.sh`.

## Goal
The Brave Search MCP was wired (launcher, key, profile registration) and looked done, but the **live
verification (2026-07-08) fails**: the `research_analyst` agent reports it has **no web/Brave search tool**,
even though the launcher fires with the key present. Make the Brave search tool actually reach the agent so
a real query returns results — the acceptance the Brave card was never truly verified against.

## Root cause (diagnosed 2026-07-08 — read before touching anything)
Isolated to **hermes↔Brave tool registration**, NOT the server or the key:
- **Server works.** Running the launcher standalone with `BRAVE_API_KEY` **exported** returns a full
  `tools/list` including `brave_web_search` (+ local/image/news/video variants). The package
  `@brave/brave-search-mcp-server` is fine.
- **Key reaches the launcher.** `~/agent-workforce/logs/brave_mcp.log` logs `key=set(len=62)` on every
  hermes run — so hermes' `env: { BRAVE_API_KEY: "${BRAVE_API_KEY}" }` interpolation resolves and the
  launcher process has the key. (`~/.hermes/.env` holds `BRAVE_API_KEY`.)
- **But the agent gets no Brave tool.** Two clean oneshot runs (`hermes -z … -p research_analyst`, no `-t`)
  both reported no web-search capability. So hermes spawns the server but never registers its tools with
  the agent.

## Most likely causes (investigate in this order)
1. **Discovery timeout too short.** `config.yaml` sets `mcp_discovery_timeout: 20`. The npx-launched Brave
   server's cold start + `tools/list` round-trip in a oneshot run may exceed 20s, so hermes drops it with
   zero tools registered (the launch is logged *before* `exec`, so a slow/failed discovery still logs
   `key=set`). Try raising it substantially and/or pre-warming; the server's own `connect_timeout: 120` is
   already generous, so the **discovery** bound is the suspect.
2. **Oneshot MCP registration.** Confirm oneshot `hermes -z` registers stdio-MCP tools the same way an
   interactive session does — check hermes' MCP discovery logs for a Brave entry / warning (the run
   `errors.log` showed only an unrelated `notion` OAuth warning, no Brave line — meaning Brave may be
   silently dropped, or discovery output goes elsewhere). Enable `hermes mcp` diagnostics if available.
3. **Persistent HTTP transport (robust fix).** The server supports `--transport http`. Running Brave as a
   small persistent HTTP service (like the qmd daemon, NUC-10) and connecting the profile via http avoids
   the per-run npx cold start entirely — the same pattern proposed for qmd in the NUC-16 qmd-transport
   brief. Strongest fix if the timeout tuning is fragile.

## Acceptance criteria
1. **The agent actually has `brave_web_search`** — a real `hermes -p research_analyst` run lists/uses the
   Brave tool (no `-t` scoping) and returns live results for a public query. Capture the query + a redacted
   result snippet + the matching `brave_mcp.log` line.
2. **Deterministic, not flaky** — repeat the run; the tool registers every time (the fix isn't a lucky race
   against a timeout). If discovery-timeout tuning is the fix, document the value + why it's sufficient.
3. **Status check reflects reality** — `praetorium-status.sh`'s Brave line already checks key + package
   resolvable (quota-free); if feasible, extend it to also flag "tool registered in last run" from
   `brave_mcp.log` + run logs, so a silent registration failure is visible. Keep it quota-free.
4. **`bash bin/verify.sh` stays green** for any in-repo change (`test_brave_status.sh` still passes).

## Files to modify
- `~/.hermes/profiles/research_analyst/config.yaml` (**outside git**) — raise `mcp_discovery_timeout`, or
  switch `brave_search` to an http transport pointing at a persistent Brave service.
- `bin/praetorium-status.sh` + `tests/test_brave_status.sh` (**git**) — only if extending the health check.
- `~/.hermes/bin/brave_mcp_launch.sh` (**outside git**) — only if it needs to `export BRAVE_API_KEY` or pass
  `--brave-api-key` explicitly (note: env passing already works in hermes per the log; likely no change).

## Test plan
- Manual (AC 1–2): two consecutive real runs both return a Brave result; capture evidence.
- `bin/verify.sh` for any status-line/test change.

## Out of scope / do not touch
- The Brave key / secrets plumbing — proven working (key reaches the launcher; server lists tools with it).
- The **fetch/headless** half — that's the NUC-22 brief; this is only the Brave **search** tool registration.
- qmd transport — parallel issue, its own brief (NUC-16 qmd-transport); note the shared "prefer a warm
  persistent service over per-run cold-spawn" theme.

## Notes / preconditions (confirmed 2026-07-08)
- `brave_mcp.log`: launches at 2026-07-07T13:22, 2026-07-08T07:58, 08:09, 08:11 — all `key=set(len=62)`.
- Standalone `tools/list` (key exported) returns `brave_web_search` with full schema — server is good.
- This flips the Brave card from "done pending verification" to "verification failed — real registration
  bug". It is the reason a full search test never passed before today.
