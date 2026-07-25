# Box-side egress paths (NUC-21 / NUC-22)

**The LLM data boundary and provider routing are NOT defined here.** Canonical source:
`03_projects/active/ai_agent_workforce/data_boundary.md` in the vault — readable from this box
through the box-safe mirror (query it via qmd). That doc is the ratified one:

> **RATIFIED 2026-07-06 · AMENDED 2026-07-08 (open-bubble posture) · RE-RATIFIED 2026-07-23
> (NUC-33 — enforceability audit + model-tier map).**

It carries the Tier 0/A/B routing rule, the ZDR provider pins, the enforced-vs-aspirational
audit, the per-job model-tier map, and the residual risks. **Do not restate any of it here.**

This file used to hold a full copy of that doc, frozen at the 2026-07-06 ratification. It missed
both later ratifications and went 19 days stale — still asserting that the box holds no
client-identifiable data, which the 2026-07-08 open-bubble decision retired. A second copy of a
policy is a copy that rots; the pointer above replaces it.

What remains below is the part canon does **not** cover: the two egress paths specific to this
box's own hardware and network position.

## Current posture in one line

The box is **inside Dave's private bubble** — the whole working vault (client names, priorities,
daily logs) is on the mirror and agents may reason over it freely. `_confidential/` is the one
data quarantine (never published, tripwired in the publish script). The one hard gate is
**no outward actions, ever** — no email, social, or messaging humans; the box holds no outward
credentials. Notion and Discord are *inside* the bubble, not outward.

**The de-identification rule survives only for what leaves the bubble** — the two egress paths
below, and any draft written for an audience outside Dave. It is a property of the outgoing
string, not of what the agent is allowed to know.

## Third-party search egress (NUC-21)

The Brave Search MCP (`@brave/brave-search-mcp-server`) adds an egress path distinct from LLM
inference: the **search query string** itself leaves the box to Brave Software Inc. (US), not
just the model's reasoning over box context.

As of NUC-21 the query egresses via a **local persistent daemon** (`brave-mcp.service`,
127.0.0.1:8766) rather than a per-run `npx` subprocess; the API key is held only by that
service (its own mode-600 `~/.config/agent-workforce/brave-mcp.env`), not injected into agent
runs. The transport change does not change the egress destination, rule, or cap below.

- **Rule:** queries must stay generic — public company/entity/person names only. Never put
  business-sensitive framing, client-identifiable strings, `_confidential/` content, or internal
  reasoning into a query. Treat this as Tier B-class egress (zero business content) regardless of
  which tier the surrounding LLM call uses. **This rule is unchanged by the open-bubble posture:**
  the box may *know* client specifics, but a Brave query is an outward string and carries none.
- **Usage cap:** Brave's Free tier is inherently self-capping — **2,000 queries/month, 1
  query/sec** — no billing to run away (NUC-08b spirit: a real spend cap is only required if Dave
  upgrades to a paid Brave plan). The agent's turn-ceiling bound (`agent.max_turns` in the profile
  config — NUC-16) also limits queries per run. Results returned are public web data.

## Direct web-fetch egress (NUC-22)

The Research Analyst's fetch capability is the built-in Hermes `browser` toolset in **local
headless-Chromium mode** (agent-browser; no Browserbase/Browser Use credential on the box). It
adds an egress path distinct from Brave search and LLM inference: the box makes a **direct HTTPS
request from its own IP** to the target URL to render JS/Cloudflare-gated pages.

- **Egress surface:** the fetched **URL** (path + query) and standard browser request headers,
  sent directly to the destination site. Unlike Browserbase, no third-party browser vendor sees
  the URL — the only party is the site being fetched.
- **Rule:** only **public, de-identified URLs** may be fetched. Never put client-identifiable
  strings, `_confidential/` content, or business-sensitive framing in a URL or query param.
  Tier B-class egress (zero business content), same discipline as the Brave query rule above.
  Also unchanged by the open-bubble posture, for the same reason.
- **No login / paywall / ToS-restricted content** — public sources only.
- **SSRF containment:** Hermes' built-in guard (`tools/url_safety.py`) blocks fetches to
  loopback / link-local / private ranges (verified: `http://127.0.0.1:8765/mcp` → not safe), so
  the fetch tool cannot be steered at the local qmd/Brave daemons or Tailscale peers.
- **Usage / spend cap:** local Chromium is **unmetered** — no per-request billing to run away
  (NUC-08b spirit); the per-run bound is `agent.max_turns` (NUC-16). The staged `BROWSERBASE_*`
  flags in `~/.hermes/.env` are dormant no-ops (no `BROWSERBASE_API_KEY`, so
  `agent/browser_registry.py` never selects the cloud backend); if Browserbase is ever keyed,
  add a session cap here first.

## Open follow-up

NUC-21 and NUC-22 are genuine parts of the data boundary and arguably belong in the canonical
vault doc rather than box-side. They are kept here for now because both describe *this box's*
hardware and network position. If they move to canon, this file becomes a pure pointer.
