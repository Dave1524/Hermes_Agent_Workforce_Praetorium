# Brief: Augustus content-automation stalls — three compounding root causes

> ## STATE — 2026-09-04: archived as a historical diagnostic, not an open work item.
>
> It records its own outcome inline: "all three fixes IMPLEMENTED & verified 2026-07-12",
> with Issue 2 (qmd semantic search CPU-bound) marked ONGOING at the time of writing.
> Kept for its measurements, which are the reason not to delete it — the per-stage
> `qmd query` timings and the three-GGUF-models-on-CPU breakdown are not recorded
> anywhere else in this repo.
>
> Read the dated facts, not the posture: this predates the Notion MCP removal (Notion is
> REST-only on this box now), so Issue 3's hard blocker no longer describes a live path.

**Date:** 2026-07-12   **Author:** diagnostic pass (Claude Code, on-box)
**Scope:** why the nightly Augustus content pitch+draft runs are slow / producing nothing.
**Evidence:** all facts below were measured live on Praetorium this session (journal, process state,
`qmd doctor`, token files, `/dev/dri` perms) — not inferred from memory.
**STATUS: all three fixes IMPLEMENTED & verified 2026-07-12** — see "RESOLUTION" at the bottom.
The card `t_c13448c9` is currently **blocked** (parked) pending one live end-to-end validation run.

> **TL;DR** Three independent problems stack on the same run: (1) the LLM model — *fixed*
> (gemma-4-26b → deepseek-v4-flash); (2) qmd semantic search runs **on CPU** because the Intel Arc
> iGPU is blocked by a missing group membership **and** a binary-selection error — every `qmd query`
> costs 100–300s; (3) the **Notion MCP HTTP stream** drops mid-run and the agent dead-stops waiting on
> it. #3 is the current hard blocker; #2 is the slow-grind tax that makes every run expensive before it
> even reaches #3.

---

## Issue 1 — Model ignoring tool instructions  ✅ FIXED
`gemma-4-26b` was not honoring tool-use instructions. Switched to `deepseek-v4-flash`. No further action;
recorded here for completeness so the timeline reads correctly.

---

## Issue 2 — qmd semantic search is CPU-bound (100–300s per query)  ⚠️ ONGOING

### What it costs (measured)
- Daemon journal (`qmd-mcp.service`), real `tools/call query` durations today:
  **102,699 ms** and **188,661 ms**.
- Augustus session `t_c13448c9` fired two `mcp__qmd__query` calls in parallel: **188.7s** and **295.7s**
  (the second nearly hit the 300s timeout) *before the agent could do anything else*.
- qmd's own warning: `QMD Warning: no GPU acceleration, running on CPU (slow)`.

### Why each `qmd query` is so heavy
`qmd query` is not a lookup — it's a **full hybrid pipeline** ("Hybrid search with auto expansion +
reranking"). One call runs **three GGUF models on CPU**:

| Stage | Model | Why it's slow on CPU |
|---|---|---|
| Query expansion (generation) | `qmd-query-expansion-1.7B` | autoregressive 1.7B decode — the dominant cost |
| Embedding | `embeddinggemma-300M` | moderate |
| Reranking (cross-encoder) | `Qwen3-Reranker-0.6B-Q8` | a forward pass per candidate doc |

Contrast: `qmd get` calls return in **4–7 ms**. The index itself is healthy (407 files / 1944 vectors,
fingerprints valid). The cost is entirely the model pipeline, not the data.

### Root cause of "CPU only" — TWO blockers, both fixable, both already 90% provisioned
The box **has** a usable GPU and **all** the software to drive it — it's simply not switched on:

- ✅ Hardware: **Intel Arc 140V iGPU** (Core Ultra 7 258V, Lunar Lake). `/dev/dri/renderD128` exists.
- ✅ Intel Vulkan driver installed: `/usr/share/vulkan/icd.d/intel_icd.json`, `mesa-vulkan-drivers`,
  `libvulkan1`.
- ✅ Vulkan-enabled llama.cpp ships inside qmd:
  `@node-llama-cpp/linux-x64-vulkan/…/libggml-vulkan.so` — and `ldd` resolves it cleanly
  (`libvulkan.so.1` found, no missing deps). The binary is fine.

Yet it runs on CPU because of two things:

1. **`dave` is not in the `render` (or `video`) group.** `/dev/dri/renderD128` is `crw-rw---- root
   render`; `test -r` → **not accessible**. So Vulkan enumerates **zero devices** for dave's processes.
2. **Forcing `QMD_LLAMA_GPU=vulkan` currently throws `NoBinaryFoundError` → falls back to CPU.**
   This is almost certainly a *consequence* of #1 (node-llama-cpp declines the Vulkan binary when no
   Vulkan device can be enumerated), not a broken binary. Fixing #1 first is the test.

Secondary smell: `qmd doctor` reports **"running on CPU (2 math cores)"** although the box has **8
cores** — llama.cpp thread count looks under-provisioned even for the CPU path.

### Fix path (ordered, lowest-risk first)
1. **Grant GPU access:** `sudo usermod -aG render,video dave`. Requires the qmd daemon (and dave's
   login) to restart to pick up the new group — do it in a quiet window (see "Coordination" below).
2. **Re-test the probe as a one-off (does not touch the live daemon):**
   `QMD_LLAMA_GPU=vulkan qmd doctor` → expect `device mode: vulkan` **without** the `NoBinaryFoundError`
   / CPU-fallback lines, and an Arc device in the probe.
3. **If step 2 is clean, make it permanent:** add a systemd drop-in to `qmd-mcp.service`
   (`Environment=QMD_LLAMA_GPU=vulkan`) and `systemctl restart qmd-mcp.service`. The unit currently has
   **no `Environment=` lines** and runs `ExecStart=/usr/local/bin/qmd mcp --http --port 8765` as
   `User=dave`.
4. **If `NoBinaryFoundError` persists after render access:** it's a node-llama-cpp backend-selection
   issue — re-fetch/rebuild the Vulkan backend for the installed qmd
   (`node-llama-cpp` download/build with `--gpu vulkan`) rather than assuming the shipped prebuilt is
   picked up. This is the only step that might need a real build.
5. **Independent of GPU — reduce the pipeline cost per query regardless:**
   - Use the **cheapest mode that suffices**. `qmd search` (BM25, *no LLM*) and `qmd vsearch`
     (vector-only, no 1.7B expansion, no rerank) return in seconds. Reserve full `qmd query` for when
     reranked hybrid quality is genuinely needed.
   - Cut the Augustus grounding step from **2–3 `qmd query` calls to 1** (see Issue-2 note in Files).
   - Consider bumping llama.cpp threads (the "2 math cores" anomaly) via qmd's thread/parallelism knobs.

**Expected impact:** GPU offload of the 1.7B expansion + reranker on the Arc iGPU should cut query time
from minutes to seconds. Even *without* GPU, dropping to 1 query and/or `vsearch` removes most of the
6–12 min grounding tax immediately.

> **Posture note:** `agent-workforce/CLAUDE.md` says "no local model runtime." qmd is the **sanctioned
> exception** — it already runs local GGUF models, indexes only the de-identified boxsafe vault, and was
> built as "vault memory for agents" (NUC-10). GPU-accelerating qmd speeds up an *existing* sanctioned
> local component; it introduces no new inference path and touches no client-identifiable data.

---

## Issue 3 — Notion MCP stream drops mid-run → agent dead-stops  🔴 CURRENT BLOCKER

### Symptom (confirmed)
Session `t_c13448c9` is **hung, not working**: process `1444131` is in `futex_do_wait`, ~8 min elapsed,
~0.5% CPU, no output. Its log dead-ends right after it fired `mcp__notion__notion_query_data_sources`
(following the two slow qmd queries) — the call never returned. Same shape as the earlier gemma run.

### What the evidence actually says about "why"
The failure is **not primarily an expired token**, and it's **not one clean failure mode** — it's two
overlapping ones:

- **The OAuth token is valid and auto-refresh works.** `~/.hermes/mcp-tokens/notion.json` was
  **rewritten at 16:20 today**, has `expires_in: 3600` and a live `refresh_token` — i.e. it refreshed
  successfully ~an hour ago and is currently valid. So "the token needs refreshing" is **largely
  disconfirmed** as the root cause of today's stalls.
- **The long-lived HTTP/SSE stream to `mcp.notion.com` drops** and the client's "reconnecting in 1000ms"
  does not always recover — the agent blocks indefinitely on the in-flight call. This matches the
  hang.
- **A large share of Notion failures are client-side, not transport.** `errors.log` is full of
  `validation_error` (HTTP 400) and `MCP error -32602: Input validation error` from
  `notion_query_data_sources` / `notion_query_database_view` / `notion_update_page` /
  `notion_update_view` — i.e. the agent calling Notion MCP tools with **malformed arguments**, plus
  `"MCP server 'notion' is unreachable after 3 consecutive failures."`

So the Notion MCP path is failing on **both** axes: a flaky stream **and** a schema the model keeps
mis-calling.

### Options (recommended order)
1. **Unblock now:** kill the hung session `t_c13448c9` (PID 1444131) and re-run. It's already
   dead-stopped, so this is low-risk — but it's a coin-flip on getting a fresh, stable stream.
   *(Recommend confirming before I kill it — see below.)*
2. **Strategic fix — move Augustus's Notion I/O off the OAuth MCP stream onto the REST integration
   token.** Per the "Notion access model" finding, the box already has a REST integration token
   `NOTION_API_TOKEN` ("Praetorium") in `secrets.env`; `agent-inbox-sync` was already migrated to it.
   REST is request/response (no long-lived stream to drop), supports exact queries / plain-text creates,
   and sidesteps both the stream drops **and** much of the MCP-schema validation churn. This is the
   durable fix; the MCP stream is the wrong transport for an unattended nightly job.
3. **Add a hard timeout + fail-open on the Notion tool** so a stalled stream can't hang the whole run —
   the agent should degrade to "board unavailable, proceed with pitch" instead of blocking in
   `futex_do_wait` forever.
4. **Deprioritize token refresh** as a fix — evidence says it's valid. Only revisit if a run fails with
   an actual 401/invalid_grant (none seen today).

---

## Why the runs "produce nothing" — the compounding picture
A single nightly run pays all three taxes in sequence: it spends **6–12 min** on CPU-bound qmd grounding
(Issue 2), *then* reaches the Notion board and the **stream drops** (Issue 3), leaving it hung with
nothing written — regardless of the model now being fixed (Issue 1). Fixing Issue 3 gets runs
*completing*; fixing Issue 2 gets them completing *fast*.

## Recommended sequence
1. **Now:** kill the hung session, re-run to unblock tonight (Issue 3, option 1).
2. **This week:** point Augustus's Notion reads/writes at the REST token (Issue 3, option 2) + add the
   tool timeout (option 3). This is what actually stops the nightly stalls.
3. **This week:** `usermod -aG render,video dave`, verify `QMD_LLAMA_GPU=vulkan qmd doctor`, then set the
   env on `qmd-mcp.service` (Issue 2, steps 1–3). Independently, cut Augustus grounding to 1 query.
4. **If needed:** rebuild node-llama-cpp Vulkan backend (Issue 2, step 4).

## Files / surfaces
- `~/.hermes/profiles/augustus/SOUL.md` — the grounding instruction that asks for 2–3 qmd queries;
  reduce to 1 and/or switch to `qmd vsearch`/`search` for cheap lookups. **(outside git)**
- `qmd-mcp.service` systemd unit — add `Environment=QMD_LLAMA_GPU=vulkan` drop-in after render access is
  granted. **(system unit)**
- Augustus Notion tool wiring — repoint to `NOTION_API_TOKEN` REST path; add call timeout. **(profile /
  toolset config, outside git)**
- Group membership: `sudo usermod -aG render,video dave` (one-time; needs daemon/login restart).

## Coordination / risk
- `qmd-mcp.service` currently serves **~16 active MCP sessions**. Restarting it (for the GPU env or after
  the group change) drops those sessions — do it during a quiet window, not mid-run.
- All Issue-2 GPU testing so far was done via **one-off CLI `qmd doctor` invocations** that spawn their
  own process and **do not touch the live daemon**. Nothing in this diagnosis has changed box state.

## Out of scope / do not touch
- qmd index / `qmd-refresh` — index is healthy; this is a device + transport problem, not a data problem.
- The canonical vault, `main` branch, publishing — unchanged; nightly writes still go through the
  agents/inbox path.

---

## RESOLUTION — implemented & verified 2026-07-12

### Issue 2 (qmd on CPU) → GPU-accelerated ✅ live
- `sudo usermod -aG render,video dave` — grants `/dev/dri/renderD128` (Arc iGPU) access.
- systemd drop-in `/etc/systemd/system/qmd-mcp.service.d/gpu.conf`:
  `Environment=QMD_LLAMA_GPU=vulkan` + `SupplementaryGroups=render video`.
- `qmd-mcp.service` restarted. **Verified live**: the daemon (node worker) holds
  `/dev/dri/renderD128` open (GPU engaged), `qmd doctor` reports `device mode: vulkan` /
  `offloading enabled` / `Intel(R) Graphics (LNL)` / 22.7 GB VRAM, and a real daemon `query`
  returned in **1.2 s** (was 100–300 s on CPU). `NoBinaryFoundError` was purely the render-group
  permission; the shipped Vulkan binary was fine all along.
- Bonus knobs found on the qmd `query` MCP tool: `rerank:false` and lower `candidateLimit` for
  cheaper calls; `qmd search` (BM25) is ~1 s; `qmd get` is ~ms.

### Issue 2b (grounding cost) → fewer/cheaper qmd calls ✅
- Card `t_c13448c9` STEP 1 rewritten to **≤2 focused `qmd query` calls** (voice, then topic), GPU-fast.
- **Correction (found during the validation run):** the *MCP* `get` tool that agents call returns
  EMPTY for every path/docid — only the **CLI** `qmd get` works. There is no `read_resource` tool
  (native `resources/read` works but isn't agent-exposed). So the original card's *"get returns
  EMPTY on this box"* warning was **correct**; agents must ground via `qmd query`. My first edit
  (telling it to use `get`) was reverted after the agent flailed on empty results mid-run.

### Issue 3 (Notion MCP stream hang) → REST migration ✅ built & tested
- New helper **`bin/notion_rest.py`** (stdlib only; reads `NOTION_API_TOKEN` from `secrets.env`;
  request/response, no long-lived stream). Commands: `board [--status]`, `pitch`, `draft`.
  Targets data source `ab5eb999-…` via `Notion-Version: 2025-09-03` (the id is a *data-source* id,
  not a database id — the "Praetorium" integration DOES have access). **Tested end-to-end**
  (create → append draft → set status → archive; board back to 0). Deployed to
  `~/agent-workforce/bin/notion_rest.py`.
- Card STEP 2/3 + TOOLS rewritten to use the helper and **forbid `mcp__notion__*`**. The notion
  OAuth `mcp_server` was left configured (idle discovery doesn't hang; only in-flight calls do) —
  physically removing it from `augustus/config.yaml` is an optional hardening follow-up.

### Validation run — DONE ✅ (run 15, 2026-07-12 17:14–17:19, 269s)
Unblocked `t_c13448c9` and let Augustus run once end-to-end. Observed live:
- Grounded via GPU-qmd — `query` calls returned in **1.3–12s** (were 100–300s on CPU).
- Board I/O entirely via **`notion_rest.py`** (`board`/`pitch`) — every call **sub-second, no hang**.
  Confirmed `notion` is gone from the worker's `--toolsets` (MCP removal took effect; gateway
  started clean).
- Completed with `kanban_complete` (no protocol violation) and **pitched 3 real, on-brand angles**
  to the Agent Content Inbox (cold-storage automation risk inversion; PM incentive-design failure;
  the dispatch-area triage test) — left in place for Dave to review.
- Only rough edge: the agent wasted ~10 turns on the empty MCP `get` before falling back to
  `query`; fixed in the card (Issue 2b) so future runs go straight to `query`.

### End state / follow-ups
- The hermes-gateway `--user` service is **running again** (started for the validation); the nightly
  card is `done` and will re-run on its normal schedule.
- Config cleanups applied: `NOTION_API_TOKEN` confirmed single (the earlier "twice" was a grep
  artifact); orphan qmd daemon on port 8799 killed; notion MCP removed from `augustus/config.yaml`
  (`.bak-notion-removed-20260712`).
- Committed to branch `debug/augustus-content-fixes-20260712`: this brief + `bin/notion_rest.py`.

### Backups
`scratchpad/card_t_c13448c9_body.orig.md` (pre-any-edit) and `…pre-notion.md` (before REST rewrite).
