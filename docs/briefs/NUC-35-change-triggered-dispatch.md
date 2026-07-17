# NUC-35 — Change-Triggered Dispatch (Shell Layer)

**Status:** Already deployed and running in production ✅  
**Effort:** M  
**Workstream:** Dispatch & triggers  
**Sprint:** Batch 1

---

## Objective

Replace the ~24h Picked→Drafted latency (Augustus discovers picked content once per night) with a sub-15-min deterministic poll that dispatches the existing Augustus draft run **only when** a new Picked row appears — spending nothing on quiet ticks.

---

## Why / Problem

The box was 100% time-triggered. Augustus discovered Picked content-board rows once per night (01:30) via `augustus-content.timer`. This meant:

- A Dave-side "Pick this angle" decision at 09:00 wouldn't be drafted until 01:30 the next day — 16.5h latency.
- Inbound webhooks are structurally impossible (Tailscale-only, no public ports).
- The correct fix is polling — but NOT an LLM as the poller (that was the NUC-25 anti-pattern: using an agent as a cron replacement).

The solution: a cheap shell/curl poll on a timer, LLM dispatched only on change.

---

## Existing Infrastructure Audit

### Already deployed and running

This ticket is **effectively complete**. All of the following are live in production:

| Component | Status | Location |
|-----------|--------|----------|
| Poll script `content_change_dispatch.sh` | ✅ Running | `~/agent-workforce/bin/content_change_dispatch.sh` (94 lines) |
| Systemd service `content-change-dispatch.service` | ✅ Deployed | `/etc/systemd/system/content-change-dispatch.service` |
| Systemd timer `content-change-dispatch.timer` | ✅ Enabled & running | `/etc/systemd/system/content-change-dispatch.timer` (every 15 min) |
| State file | ✅ Persists | `~/agent-workforce/var/content_picked.state` |
| Picked-state diff | ✅ Deterministic, model-free | Uses `notion_rest.py board --status Picked --json` + `grep -Fxv -f` diff |
| Fail-soft on API error | ✅ No state corruption on transient failure | Exits 0, leaves state untouched |
| Flock safety with nightly run | ✅ `agent_propose.sh` has flock at `/tmp/agent_propose.lock` | Overlap with 01:30 nightly = clean SKIP, no double-draft |
| Logging | ✅ Active | `~/agent-workforce/logs/content_change_dispatch.log` |

**Evidence from logs (2026-07-17):**
```
15:00:57 no new Picked rows (0 currently Picked) — refreshing state, no dispatch
15:16:14 no new Picked rows (0 currently Picked) — refreshing state, no dispatch
15:32:03 no new Picked rows (0 currently Picked) — refreshing state, no dispatch
...
```
Steady-state: one Notion REST query + one file diff = essentially zero cost per tick.

### Implementation approach used (for reference)

1. **Poll:** `content-change-dispatch.timer` fires every 15 min (`OnCalendar=*:0/15`)
2. **Read:** Calls `python3 notion_rest.py board --status Picked --json` — a deterministic REST call, no LLM
3. **Diff:** Compares current Picked page IDs against a plaintext state file (`grep -Fxv -f`)
4. **Dispatch only on change:** If new IDs appear, runs `agent_propose.sh` (same wiring as the nightly `augustus-content.service`)
5. **Advance state only after success:** State file updated only after a successful dispatch
6. **Fail-soft:** Any Notion API error → log + exit 0 (state untouched, retry next tick)

### Remaining gaps (minor)

| Gap | Detail | Effort |
|-----|--------|--------|
| No explicit unit test for the diff logic | The polling + diff logic is not covered by a test | S (could add a test similar to `batch1/tests/test_content_change_dispatch.sh`) |
| Scorecard coverage | `bin/scorecard.sh` might not track dispatch latency reduction | S |
| Documentation | No doc in `docs/` describing the dispatch pattern for future agent types | XS |

---

## Remaining Work

### Step 1 — Update Sprint Board status

**This ticket should be marked Done on the Sprint Board.** The implementation is live and verified. Move it to Done to reflect reality.

### Step 2 — (Optional) Add a simple test

If there's a test infrastructure to add to, create a test that stubs Notion responses and verifies the diff logic:

```bash
# Simulate: state file has ID "abc", current response has "abc" + "def"
# Expect: dispatch fires for "def"
```

See `~/dev/agent-workforce-batch1/tests/test_content_change_dispatch.sh` for the existing pattern.

### Step 3 — (Optional) Document for reuse

The change-triggered dispatch pattern is general: shell poll → REST query → diff → dispatch. If other agent types (beyond Augustus content) need the same pattern, document it in a brief `docs/change_dispatch_pattern.md`.

---

## Files Touched

| File | Action | Status |
|------|--------|--------|
| `bin/content_change_dispatch.sh` | Already created | ✅ Done |
| `systemd/content-change-dispatch.service` | Already created | ✅ Done |
| `systemd/content-change-dispatch.timer` | Already created | ✅ Done |
| `/etc/systemd/system/content-change-dispatch.{service,timer}` | Already deployed | ✅ Live |
| `~/agent-workforce/var/content_picked.state` | Already auto-created | ✅ Live |
| Sprint Board | **Update NUC-35 status → Done** | ⬜ Pending |
| `docs/change_dispatch_pattern.md` | Create (optional, for reuse) | ⬜ Optional |

---

## Verification

Verified live on the box:

```bash
# Check timer is active
sudo systemctl status content-change-dispatch.timer

# Check recent runs
tail ~/agent-workforce/logs/content_change_dispatch.log

# Test manually (dry run — no new Picked rows, should just refresh state)
sudo systemctl start content-change-dispatch.service
```

---

*Brief generated 2026-07-17. Based on Notion NUC-35 spec + box audit. This ticket is already in production — brief covers verification + remaining optional steps.*
