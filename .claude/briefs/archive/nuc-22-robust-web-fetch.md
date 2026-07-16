# Brief: NUC-22 — Robust web-fetch for the Research Analyst (Cloudflare/JS fallback)
**Date:** 2026-07-08   **Verify:** `bash bin/verify.sh` (run from `~/dev/agent-workforce/` repo root)

> **Where this runs:** agent-workforce repo on Praetorium (`~/dev/agent-workforce`); run `/implement` on
> the box. Live MCP/profile wiring is outside git (`~/.hermes/profiles/research_analyst/config.yaml`,
> `~/.hermes/.env`, `~/.config/agent-workforce/secrets.env`) — edit those directly on the box, never commit.
>
> **Deploy note (NUC-16):** runtime executes `~/agent-workforce/bin/…`; after committing, `cp` changed
> `bin/` scripts to `~/agent-workforce/bin/` (+ `~/deploy-staging/…`).

## Goal
The Research Analyst's **search** half is handled — Brave Search MCP is wired and, as of this session,
live-verified (the separate NUC-21/Brave card). What remains from the original NUC-22 gap is **fetch**:
NUC-15's first real run flagged **Cloudflare-blocked sources** and couldn't complete parts of its research.
Brave returns result snippets + URLs; it does not render a JS/Cloudflare-gated **page body**. Give the
profile a robust fetch capability so a source that previously blocked it now completes — degrading
gracefully (skip + note the gap) rather than fabricating. Source: Hermes masterclass §7 (Brave / Puppeteer),
evidenced by NUC-15's 2026-07-07 run note.

## Investigate first (do NOT add machinery before confirming the gap)
- The `research_analyst` profile registers only `qmd` + `brave_search` MCPs, but **Hermes ships built-in
  web/browser toolsets** (`WEB_TOOLS_DEBUG`, browser tools) and `secrets.env` already holds staged
  **Browserbase** config (`BROWSERBASE_ADVANCED_STEALTH`, `BROWSERBASE_PROXIES`, `BROWSER_*` timeouts).
  So the capability may be **partly present already**. Before wiring a new fetch MCP, check what fetch/
  browser tools the profile actually has (`hermes -p research_analyst`, `-t`/toolset config; `hermes tools`)
  and whether the staged Browserbase path is reachable. Prefer enabling/using an existing tool over adding a
  new always-on service (mirrors the Brave decision: no new service unless needed).

## Acceptance criteria
1. **A robust fetch tool is available to the profile** — either an existing Hermes browser/fetch toolset
   (enabled + keyed via the staged Browserbase config) or, only if needed, a fetch MCP with a real UA +
   headless-browser fallback for JS/Cloudflare pages. Registered the same stdio/toolset way as qmd/Brave.
2. **Secrets discipline (NUC-12)** — any key stored in `~/.config/agent-workforce/secrets.env` (source of
   truth, mode 600, never committed) and mirrored to `~/.hermes/.env` only if the runtime needs it in
   `os.environ` (same plumbing pattern the Brave key uses).
3. **Box-safe egress (NUC-07b)** — only public/de-identified URLs and queries leave the box. The fetched
   **URL + any query** is the egress surface; document this in `docs/data_boundary.md` as a new path
   (extends the Brave "third-party search egress" section), and cap/spend-bound it if the fetch backend is
   metered (Browserbase is — note its session limits; mirror NUC-08b spirit).
4. **A previously-blocked source now completes** — reproduce the NUC-15 failure mode: point a run at a
   source set that previously Cloudflare-blocked it; the run now retrieves usable content. Capture the
   command + redacted evidence.
5. **Graceful degradation preserved** — when a source still can't be fetched, the agent skips it and notes
   the gap in its proposal rather than fabricating — preserve the honesty behavior NUC-15 already showed.
   Do not let a fetch failure abort the whole run.
6. **`praetorium-status.sh` (NUC-18) extended** — a lightweight, quota-free reachability check for the fetch
   backend (config present / resolvable), consistent with the Brave and qmd health lines. Cover it in a
   `tests/*.sh` like `test_brave_status.sh` does.
7. **`bash bin/verify.sh` stays green** — syntax + `shellcheck -S error` clean over `bin/*.sh`, every
   `tests/*.sh` exits 0.

## Files to modify (git-tracked)
- `bin/praetorium-status.sh` — add a fetch-backend health line (AC 6), same shape as the Brave section.
- `docs/data_boundary.md` — add the fetch egress path + usage/spend cap (AC 3), next to the Brave section.
- `docs/runbook.md` — note the fetch capability + how to test it.

## Files to create (git-tracked)
- `tests/test_fetch_status.sh` — mocked status-line test (no network, no real key), mirroring
  `tests/test_brave_status.sh`.
- Only if a wrapper/launcher is genuinely needed (like `brave_mcp_launch.sh`): a small launch script under
  `bin/` + its diagnostic log. Avoid if a built-in toolset suffices.

## Live box config to change (outside git — edit directly on the box)
- `~/.hermes/profiles/research_analyst/config.yaml` — enable the fetch toolset / register the fetch MCP.
- `~/.config/agent-workforce/secrets.env` + `~/.hermes/.env` — any required key (Browserbase etc.), mode 600.

## Test plan
- `tests/test_fetch_status.sh` proves the status line reports reachable/unreachable correctly, via `verify.sh`.
- Manual reproduction (AC 4 + 5): a real run over a previously-Cloudflare-blocked source completes and, where
  a source still fails, the proposal notes the gap (no fabrication). Redacted evidence in the runbook.

## Out of scope / do not touch
- The **search** half (Brave) — already wired + verified; don't re-do it. Reconcile the duplicate card
  numbering when finalizing the board (this was tangled with the "NUC-21 Add Brave Search MCP" card).
- A generic filesystem MCP or broad browser automation — keep writes narrowed to `_inbox/agents/**`; a fetch
  tool reads the web, it must not widen the agent's write surface.
- Scraping behind logins / paywalled or ToS-restricted content — public sources only.
- No client-identifiable strings in fetched URLs or queries.

## Notes / preconditions (confirmed on the box 2026-07-08)
- Brave Search MCP: launcher `~/.hermes/bin/brave_mcp_launch.sh`, key present in `~/.hermes/.env`, registered
  in the profile, `test_brave_status.sh` green. Its remaining item is the live search verification (handled
  this session), not more build.
- Browserbase config already staged in `secrets.env` (`BROWSERBASE_ADVANCED_STEALTH`, `BROWSERBASE_PROXIES`,
  `BROWSER_SESSION_TIMEOUT`, `BROWSER_INACTIVITY_TIMEOUT`) — investigate whether this already backs a Hermes
  browser tool before adding anything.
- Keep the runner guardrails intact; no `--max-turns` (NUC-16 — hermes `-z` has none; ceiling is the profile
  config `agent.max_turns`).
