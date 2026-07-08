# Brief: NUC-16 — Wire research_analyst qmd to the warm HTTP daemon (unblock useful proposals)
**Date:** 2026-07-08   **Verify:** `bash bin/verify.sh` (agent-workforce repo) + a live proposal run

> **Where this runs:** the live fix is a **profile-config change outside git**
> (`~/.hermes/profiles/research_analyst/config.yaml`), plus a possible `praetorium-status.sh` health line
> in the agent-workforce repo. Run `/implement` on the box; iterate live (change config → `hermes -p
> research_analyst` test → confirm qmd search returns → revert if broken). A bad qmd config breaks the
> whole profile, so test each change against a real hermes run before committing.

## Goal
The NUC-16 wrapper pipeline is fixed and proven (phantom `--max-turns` removed 2026-07-08 — the run now
executes hermes end-to-end, fails safe, logs cost). But the **first real run produced no proposal because
qmd timed out**: the agent reported *"qmd query service is timing out (120s timeout on search queries); I
cannot read the priority/loop files."* Fix the qmd wiring so the agent can actually read vault context and
produce its first useful proposal — the true acceptance of NUC-16.

## Root cause (fully diagnosed 2026-07-08)
- qmd is **healthy and fast**: `qmd status` = 100 files / 517 vectors indexed; a CLI `qmd search` returns in
  **~0.3s**; `qmd-refresh.timer` is updating the index every 30 min.
- NUC-10 runs qmd as a **warm HTTP daemon**: `qmd-mcp.service` → `qmd mcp --http --port 8765`, up 1d16h,
  `/health` returns 200 in ~1.7ms. It was built expressly as "vault memory for agents."
- **But the profile registers qmd as stdio** (`qmd: { command: "qmd", args: ["mcp"], timeout: 120 }`), so
  every run spawns a **fresh `qmd mcp` subprocess**. Its `initialize` handshake is fast, but the **first
  semantic `search` call cold-loads the embedding model per run**, blowing past the 120s call timeout. The
  agent never reaches the warm daemon.

## Acceptance criteria
1. **The profile's qmd MCP uses the warm HTTP daemon** (port 8765) instead of spawning a cold stdio server —
   OR, if HTTP transport in the profile config proves unworkable, the stdio path is made fast (pre-warmed /
   persistent embedding model) so a `search` call returns well within the timeout. Prefer the daemon: it
   already exists and is warm.
2. **A real run reads vault context and produces a proposal** — re-run `agent_propose.sh`; the agent
   successfully qmd-searches priorities/open-loops/daily-log and writes one proposal to
   `_inbox/agents/YYYY-MM-DD_<slug>.md` (or a legitimate reasoned "nothing qualifies", but qmd must succeed).
3. **qmd health surfaced** — `praetorium-status.sh` (NUC-18) shows the profile's qmd path is the reachable
   daemon, not a cold-spawn (extend the existing qmd status line). Covered by a `tests/*.sh`.
4. **Timer goes live only after a clean useful run** — once AC 2 passes, `sudo systemctl enable --now
   agent-proposal.timer` (Mon–Fri 06:30, Persistent=true). Do NOT enable before, or every scheduled run
   burns an API call to produce "no proposal — qmd timeout".
5. **`bash bin/verify.sh` stays green** for any in-repo changes (status line + test).

## Investigate first
- Confirm the profile-config `mcp_servers` block accepts an `http` transport (`type: http` + `url:`), as the
  catalog layer does (`hermes_cli/mcp_catalog.py`: transport.type ∈ {stdio, http}). Find the exact endpoint
  path the daemon serves MCP on (`/mcp` returns 400 to a bare GET — it needs a proper MCP client handshake;
  the correct URL is likely `http://127.0.0.1:8765/mcp` with streamable-http). Check `hermes mcp` help / any
  existing http-MCP example.
- If the profile format only supports stdio, check whether `qmd mcp` has a flag to attach to the running
  daemon / reuse a warm model, or whether the embedding model can be pre-pulled so the cold path is fast.

## Files to modify
- `~/.hermes/profiles/research_analyst/config.yaml` (**outside git**) — repoint the `qmd` MCP entry to the
  HTTP daemon. Keep `brave_search` unchanged.
- `bin/praetorium-status.sh` (**git**) — qmd health line reflects the daemon path (AC 3).

## Test plan
- Manual (AC 2): a real `agent_propose.sh` run completes with qmd reads succeeding — capture `agent_run.log`
  showing successful qmd search + a proposal (or reasoned no-proposal after real reads).
- `tests/test_*.sh` for the status line, via `verify.sh`.

## Out of scope / do not touch
- The wrapper guardrails (flock, retry/backoff, write-boundary, cost logging) — already correct; don't regress.
- Do NOT reintroduce `--max-turns` (hermes `-z` has none; ceiling is `agent.max_turns` in the profile config).
- qmd indexing / `qmd-refresh` (NUC-10) — the index is healthy; this is purely a transport-wiring fix.
- Brave MCP — separate; already wired + launching with the key.

## Notes / preconditions (confirmed on the box 2026-07-08)
- Latest run: `outcome=OK run_seconds=380 attempts=1`; agent explicitly blocked on qmd timeout; no proposal.
- Minor metrics bug for NUC-23: `cost.log` logs `model=anthropic/claude-sonnet-5` (echoing
  `LLM_MODEL_BUSINESS`) while the profile actually runs `anthropic/claude-haiku-4.5` (profile config) — the
  cost.log model field is unreliable; fix under NUC-23, not here.
- Deploy note: runtime executes `~/agent-workforce/bin/…`; `cp` any changed `bin/` script there after commit.
