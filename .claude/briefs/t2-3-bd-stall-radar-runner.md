# Brief: T2.3 — bd-stall-radar CC runner and suite
**Date:** 2026-09-09   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 1. Red lines equal T1.1's ten `contract-exists` paths, plus any drift this task's own `bin/deploy` clears.

Task bullet, `docs/dev-plan-2026-09.md:96`: *"bd-stall-radar runner: `bin/run_bd_stall_radar_cc.sh` on the m1 pattern around `bin/bd_stall_radar_kernel.py`; a smoke suite; `profiles/bd_stall_radar.env.example` with `AGENT_VERIFY_CMD`; the manifest's `runner` field. Existing brief: `.claude/briefs/bd-radar-followup-timers.md`. Gate: verify green; the unit stays disabled."* Size M, no blocker.

The 2026-09-01 brief still describes the runner shape and the task-file qmd→disk amendment. It is otherwise stale: W1 split `AGENT_PROFILE` (runtime) from `AGENT_OWNER` (persona); T2.2 takes runners off `bypassPermissions`; enablement and live probes are T2.4 + D1, not this task. This file is the brief that executes.

## Why

The live override still execs `bd_stall_radar_kernel.py` directly. There is no CC runner, no `profiles/*.env.example`, no suite, no manifest `runner`. T1.2 therefore skips the row. The kernel stays the stall detector — exact rules, $0, no model. The new runner is the m1-shaped harness around it so agent_propose.sh, `AGENT_VERIFY_CMD`, and the no-MCP flags apply.

## What to land

| Piece | Shape |
| --- | --- |
| `bin/run_bd_stall_radar_cc.sh` | m1: `[ -r task ]`, `cd` inbox, `claude -p` with the task file. `--model claude-sonnet-5`, `--permission-mode dontAsk` (T2.2), `--strict-mcp-config`, empty mcpServers, `--allowedTools "Bash,Read,Write,Edit,Glob,Grep"` (claudius scheduled floor; T1.2 joins it). No vault_sync_guard. |
| `profiles/bd_stall_radar.env.example` | `AGENT_PROFILE=claude-sonnet`, `AGENT_OWNER=claudius`, `AGENT_TASK_SLUG=bd-stall-radar`, `AGENT_MAX_ATTEMPTS=2`, `AGENT_RUNTIME_CMD` → the new runner, `AGENT_VERIFY_CMD='~/agent-workforce/bin/proposal_or_decline.sh bd-stall-radar'`, `AGENT_MCP_DEPS=none`. |
| `tests/test_bd_stall_radar_smoke.sh` | Offline, mock claude, HOME fixture. Env parse, missing task/inbox refuse, argv (model, no MCP, no web, dontAsk), task guards, kernel path, unit files. Does not talk to the live box. |
| `design/agents/claudius.toml` | `runner`, `suite`, `model = "claude-sonnet-5"`, `web = false`. Status stays `dormant`. |
| `profiles/bd_stall_radar_task.md` | Point at the kernel; qmd → disk read of `~/vault/04_operations/current_priorities.md`; keep Stage / parked / no-Notion-writes guards; drop the Hermes `memory` tool (kernel appends MEMORY.md; under dontAsk a missing tool fails the run). |
| `bin/bd_stall_radar_kernel.py` | Print `DECLINE: no genuine new stalls, no proposal written` on a clean decline so `proposal_or_decline.sh` can see `^DECLINE:` in the run log. |

## Acceptance criteria

1. `python3 tests/test_workflow_coverage.py`: no new PROBLEM on this row (tools = scheduled floor, model matches, mcp empty). Red list remains T1.1's ten paths.
2. `tests/test_bd_stall_radar_smoke.sh` green.
3. `bash bin/verify.sh` exit 1; red = those ten paths, plus drift this deploy clears.
4. `systemctl is-enabled bd-stall-radar.timer` is still `disabled`. Do not start the service. Do not copy an env into `~/.config/agent-workforce/` (D1, deny-listed).

## Runtime actions

```
bin/deploy
```

No unit install, no enable, no live run. T2.4 does those after D1.

## Out of scope / do not touch

- T2.4, D1, enabling either BD timer, `profiles/bd_followup_drafts.env.example` `AGENT_PROFILE` line.
- Timer OnCalendar values, Stage/parked/no-Notion-writes guard clauses as rules.
- `.claude/briefs/current.md` and `.claude/briefs/archive/`.
- `~/.config/agent-workforce/**`.
- No `sudo`, no `bin/deploy --prune`.
