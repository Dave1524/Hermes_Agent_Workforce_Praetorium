# Remote-LLM data boundary & provider routing (NUC-07b)

**Status: RATIFIED by Dave (2026-07-06).** This rule is the confidentiality firewall that replaced
the dropped local-model tier. It sits alongside the `_confidential/` rule: that rule decides what
may exist on the box; this rule decides what may egress from it, and to whom.

## The routing rule

**Tier A — business-sensitive (the default for anything using vault context):**
- Path: OpenRouter, strict pin — all four flags on every request:
  `provider.zdr: true` + `provider.data_collection: "deny"` + `provider.only: [<approved list>]`
  + `provider.allow_fallbacks: false`. Any one omitted reopens a silent fallback leak.
- Model pin (set 2026-07-06 against the live ZDR list): `anthropic/claude-sonnet-5`, ZDR-served
  via Amazon Bedrock and Azure (`provider.only: ["amazon-bedrock", "azure"]`). Anthropic-direct
  is not ZDR-listed on OpenRouter. Re-check the live list if the pin ever changes.
- Account backstop: enable the account-level ZDR toggles at openrouter.ai/settings/privacy.

**Tier B — generic bulk only (zero business content, zero vault context):**
- Model pin (set 2026-07-06): `deepseek/deepseek-v4-flash` via OpenRouter with `zdr: true` +
  `data_collection: "deny"` — it has 11 Western ZDR hosts (DeepInfra, Fireworks, …), so bulk
  traffic never routes to China at all. China-direct APIs remain acceptable only for content Dave
  would post publicly (PRC storage, no fixed retention period, opt-out training).

**Hard rules (both tiers):**
1. OpenRouter prompt-logging and the "1% discount" data-sharing opt-ins are **never enabled** —
   opting in grants OpenRouter a perpetual, irrevocable commercial license (ToS §6.2).
2. What may egress = content retrievable via qmd from the box-safe mirror (de-identified by
   construction) for the task at hand. Agents query qmd per task; they never bulk-dump folders
   into prompts.
3. What may never egress: client-identifiable material (not on the box at all), secrets, and
   `_confidential/` (absent + qmd-excluded — the NUC-10 exclusion test is the release gate).
4. Spend: per-key hard credit limit at OpenRouter (NUC-08b) — also the runaway-loop backstop,
   because Hermes' `model.max_tokens` is broken on OpenAI-compatible endpoints (issues
   #4404/#20741); the runaway bound is the profile config `agent.max_turns` ceiling + the key cap.

## Residual risks accepted at ratification

- OpenRouter remains a US-based transit intermediary (ToS §6.1 processing license, metadata,
  legal-process exposure) even with all flags set.
- OpenRouter's ZDR/data-policy tags are "best knowledge", not warranties; the sub-processor
  behind a ZDR-tagged frontier model may be Azure/Vertex — verify on the model page when keying.
- 30-day retention (e.g. Anthropic direct default) is low-retention, not zero — ZDR-tagged
  endpoints are the target for Tier A.

## Third-party search egress (NUC-21)

The Brave Search MCP (`@brave/brave-search-mcp-server`) adds an egress path distinct from LLM
inference: the **search query string** itself leaves the box to Brave Software Inc. (US), not
just the model's reasoning over box-safe context.

- **Rule:** queries must stay generic — public company/entity/person names only. Never put
  business-sensitive framing, client-identifiable strings, `_confidential/` content, or internal
  reasoning into a query. Treat this as Tier B-class egress (zero business content) regardless of
  which tier the surrounding LLM call uses.
- **Usage cap:** Brave's Free tier is inherently self-capping — **2,000 queries/month, 1
  query/sec** — no billing to run away (NUC-08b spirit: a real spend cap is only required if Dave
  upgrades to a paid Brave plan). The agent's turn-ceiling bound (`agent.max_turns` in the profile
  config — NUC-16) also limits queries per run. Results returned are public web data.

## Rationale

The box-safe repo (boundary 1) decides what data may exist on the NUC. With no local model tier,
everything an agent reasons over egresses to an API (boundary 2). Ratified position: box-safe
business content may go to Western zero-retention/no-train endpoints — consistent with existing
Claude/OpenAI practice — while China-direct models are reserved for public-grade bulk work.
