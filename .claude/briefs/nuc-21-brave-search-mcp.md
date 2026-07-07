# Brief: NUC-21 — Add Brave Search MCP for research profiles
**Date:** 2026-07-07   **Verify:** `bash bin/verify.sh` (run from `~/dev/agent-workforce/` repo root)

> **Where this runs:** the agent-workforce repo lives **only on Praetorium** (`~/dev/agent-workforce`,
> no GitHub remote). Run `/implement` in a Claude Code session on the box (SSH `praetorium`, `cd ~/dev/agent-workforce`).
> This brief was authored from the Mac vault session but targets the box — the vault has no verify gate.

## Two surfaces (read this first)
This feature touches two places, and only one of them is git-tracked:

1. **Git-tracked, gated by `bin/verify.sh`** — inside `~/dev/agent-workforce/`:
   `bin/praetorium-status.sh`, `docs/data_boundary.md`, and a new `tests/*.sh`. These get committed.
2. **Live box state, OUTSIDE this repo — never committed** — the actual MCP wiring:
   `~/.config/agent-workforce/secrets.env`, `~/.hermes/.env`, and
   `~/.hermes/profiles/research_analyst/config.yaml`. Edit these directly on the box.
   Same discipline as CLAUDE.md "Secrets are a separate tree" and the NUC-08b brief's treatment of `~/.config/agent-workforce/`.

The verify gate proves the in-repo scripts are sound; the **manual search test (AC 6)** proves the live wiring works. Both are required for "done".

## Acceptance criteria
1. **Brave API key obtained & stored (secrets discipline, NUC-12).** A Brave Search API key (free tier)
   is present in `~/.config/agent-workforce/secrets.env` as `BRAVE_API_KEY=...`, file mode `600`, never committed.
   *(This is the source-of-truth copy; see AC 3 for the runtime copy.)*
2. **Brave Search MCP server runs via `npx`, reading the key from env** — no new always-on systemd service.
   Use the official current package **`@brave/brave-search-mcp-server`** (npm v2.0.85; STDIO is its default transport;
   requires `BRAVE_API_KEY`). **Not** the older `@modelcontextprotocol/server-brave-search` (npm-deprecated,
   "no longer supported" — this is what the Mac's `~/.claude.json` still uses; the box should use the official one).
3. **Registered in the `research_analyst` Hermes profile**, same stdio pattern as the existing `qmd` MCP (NUC-14),
   in `~/.hermes/profiles/research_analyst/config.yaml` under `mcp_servers:`, with the key passed through the
   server's `env:` block via `${BRAVE_API_KEY}` interpolation (see "Runtime key plumbing" below).
4. **Guardrail documented in `docs/data_boundary.md`**: the search **query string itself** is a new third-party
   egress path (distinct from LLM inference) to Brave Software Inc. (US). Profiles must keep queries generic —
   public company/entity/person names only — never business-sensitive framing, client-identifiable strings,
   `_confidential/` content, or internal reasoning. Extends the NUC-07b boundary to this new egress surface.
5. **Usage cap noted** (NUC-08b spirit, scoped to query volume): document the Brave **Free tier ceiling
   (2,000 queries/month, 1 query/sec)** in `data_boundary.md` and as a comment near the config stanza. Free tier
   is inherently self-capping (no billing to run away); the agent's existing `--max-turns` bound (AGENT_MAX_ITERATIONS)
   limits queries per run. Note that a real spend cap becomes required only if Dave upgrades to a paid Brave plan.
6. **Manual test passes**: the `research_analyst` profile runs a real search query through the Brave MCP and gets
   results back. Capture the command + a redacted snippet of results as evidence.
7. **`praetorium-status.sh` (NUC-18) extended** to show whether the Brave MCP is reachable, consistent with existing
   service-health checks — a lightweight, **quota-free** check (key configured + server package/`npx` resolvable),
   never issuing a live billed search on a routine status run.
8. **`bash bin/verify.sh` stays green** (bash `-n` syntax + `shellcheck -S error` clean over `bin/*.sh` + every `tests/*.sh` exits 0).

## Runtime key plumbing (the one non-obvious part — get this right)
Hermes' MCP launcher (`~/.hermes/hermes-agent/tools/mcp_tool.py`) does **not** forward arbitrary parent-process env
vars to stdio MCP subprocesses. `_build_safe_env()` passes only an allowlist (`PATH/HOME/USER/LANG/...`, `XDG_*`)
**plus whatever is in the server config's `env:` block**. Config `${VAR}` / `${env:VAR}` placeholders are resolved by
`_interpolate_env_vars()` via `agent.secret_scope.get_secret()`, which (single-profile / non-multiplex deployment,
the current mode) reads `os.environ`.

Therefore the key must be **(a)** declared in the server's `env:` block as `${BRAVE_API_KEY}`, **and (b)** present in
the hermes process's `os.environ` at startup. Hermes loads `~/.hermes/.env` into the environment — that file already
holds the **active** `OPENROUTER_API_KEY` (the profile `.env` is empty; `secrets.env` is only read by
`agent_propose.sh`'s preflight gate, not by hermes at runtime).

**Recommended design (mirror the existing OPENROUTER_API_KEY pattern — least blast radius):**
- `secrets.env` → `BRAVE_API_KEY=...` (source of truth / secrets discipline, AC 1)
- `~/.hermes/.env` → `BRAVE_API_KEY=...` (the copy hermes actually loads → interpolation resolves)
- `config.yaml` `env: { BRAVE_API_KEY: "${BRAVE_API_KEY}" }` resolves from `os.environ` → passed to the npx subprocess.

This duplicates the key across two files exactly as `OPENROUTER_API_KEY` is duplicated today (accepted pattern).
Alternative considered and **not** chosen for this brief: wrapping the `source "$SECRETS"` in `agent_propose.sh` with
`set -a`/`set +a` to export secrets into `os.environ` (single source of truth) — cleaner, but it modifies the
guardrailed NUC-08b/16 runner, and it wouldn't cover a manual `hermes -p research_analyst` test launched from an
interactive shell (AC 6). If Dave prefers the single-source approach, that's a small follow-up, not this task.

## Live box config to change (outside git — edit directly on the box)
- `~/.config/agent-workforce/secrets.env` — add `BRAVE_API_KEY=...`; confirm mode stays `600`. Never `git add`.
- `~/.hermes/.env` — add `BRAVE_API_KEY=...` (runtime read; mirrors the active `OPENROUTER_API_KEY` line already there).
- `~/.hermes/profiles/research_analyst/config.yaml` — add a sibling to `qmd` under `mcp_servers:`:
  ```yaml
  mcp_servers:
    qmd:
      command: "qmd"
      args: ["mcp"]
      timeout: 120
    brave_search:
      command: "npx"
      args: ["-y", "@brave/brave-search-mcp-server"]   # STDIO is the default transport
      env:
        BRAVE_API_KEY: "${BRAVE_API_KEY}"
      timeout: 120
      connect_timeout: 120   # first npx run downloads the package; give the cold start headroom
  ```
  Pre-warm once to avoid a first-connect timeout: `npx -y @brave/brave-search-mcp-server --version`.

## Files to modify (git-tracked)
- `bin/praetorium-status.sh` — add a `── Research MCP (Brave)` section after the `── qmd index` block. Lightweight,
  quota-free, and shellcheck-`error`-clean (quote all expansions; the script runs under `set -uo pipefail`, no `-e`,
  so guard unset vars). Report two lines, e.g.:
  - `key`: `set` if `BRAVE_API_KEY` is present (grep `~/.hermes/.env` for an uncommented `BRAVE_API_KEY=`, or test the
    env var), else `MISSING`.
  - `server`: `resolvable` if `command -v npx` succeeds, else `npx-missing` (do **not** run a live search here).
  Optionally gate a real probe behind an explicit `--probe`/env flag so a routine status run never spends quota.
- `docs/data_boundary.md` — add a short subsection (e.g. `## Third-party search egress (NUC-21)`) covering AC 4 + AC 5:
  the query string is the egress surface; generic-public-identifiers-only rule; Tier B-class; Free-tier cap (2,000/mo, 1 rps);
  results are public web data.

## Files to create (git-tracked)
- `tests/test_brave_status.sh` — makes the gate meaningful for AC 7 without network/quota. Mirror the mocking discipline
  of `tests/test_agent_propose_smoke.sh`: put stub `npx`, `systemctl`, `qmd`, `tailscale`, `git`, `free`, `uptime`, `df`
  on a scratch `PATH`, and run `bin/praetorium-status.sh` under two scenarios, asserting on captured stdout + exit code:
  1. `BRAVE_API_KEY` set (via stub `~/.hermes/.env` or env) → output contains the Brave section and reports `key=set`,
     `server=resolvable`; script exits 0.
  2. `BRAVE_API_KEY` absent → section still prints and reports `key=MISSING`; script exits 0.
  Must not require network access, a real key, or a live search.

## Test plan
- `bash bin/verify.sh` from `~/dev/agent-workforce/` — must exit 0 (syntax + `shellcheck -S error` clean + `tests/*.sh`
  incl. the new `test_brave_status.sh` all pass).
- **Manual live test (AC 6, box, real key required):** run the `research_analyst` profile and issue one real query, e.g.
  `~/.local/bin/hermes -p research_analyst -z "search the web for: Rhenus logistics business unit — return 3 result titles+URLs"`
  (or the profile's normal entrypoint). Confirm the Brave MCP tool is discovered and returns real results. Record the exact
  command + a redacted result snippet in the implementation notes / today's daily log. This is the acceptance the mocked
  test cannot cover.
- `bash bin/praetorium-status.sh` on the box — confirm the new Brave section renders with the live key present.

## Out of scope / do not touch
- **GitHub MCP and Filesystem MCP** — explicitly deferred in the NUC-21 scoping conversation (2026-07-07). Do not add either.
- Do not add an always-on systemd unit for Brave (AC 2: `npx` stdio, on-demand only). Do not enable
  `agent-proposal.timer`/`.service` (that's NUC-16's switch).
- Do not modify Hermes tool code under `~/.hermes/hermes-agent/` — that's upstream, not ours.
- Do not `git add` anything from `~/.config/agent-workforce/`, `~/.hermes/.env`, or the profile `config.yaml` — all
  outside this repo by design.
- Do not change the `qmd` server entry, the model/provider config, or `agent.max_turns` in the profile.
- Do not switch the Brave server to HTTP transport (STDIO default is correct here; no port to manage).

## Notes / preconditions
- **Human precondition — Dave must obtain the Brave API key** before AC 1/6/7 can be fully satisfied. Free plan:
  https://brave.com/search/api/ ("Data for Search" / free tier, 2,000 queries/month, card may be required to activate).
  `/implement` can wire everything else, but the **manual search test (AC 6) can only pass once the key is in place** —
  if the key isn't ready at implement time, land the in-repo changes (status script + docs + test → gate green) and
  defer only AC 6 with a clear note; do not fake a passing search.
- The `research_analyst` profile is runnable today: NUC-07b is **RATIFIED** (2026-07-06, per `docs/data_boundary.md`),
  `OPENROUTER_API_KEY` is set, `AGENT_RUNTIME_CMD` points at this profile, and the OpenRouter per-key credit cap is set
  (NUC-08b). So a live search test is feasible.
- The prior `current.md` (NUC-08b cost-guardrail) is **complete** (committed `ec8d203`) and has been archived to
  `.claude/briefs/archive/2026-07-07-nuc-08b-cost-guardrail.md`; its canonical copy remains at
  `.claude/briefs/nuc-08b-cost-guardrail.md`.
- Existing MCP-registration reference (the NUC-14 pattern this copies): `~/.hermes/profiles/research_analyst/config.yaml`
  currently registers `qmd` as `command: "qmd" / args: ["mcp"] / timeout: 120`.
- Roster/naming: keep the box-side conventions (Praetorium / Marcus); this adds a tool to an existing profile, no new agent.
