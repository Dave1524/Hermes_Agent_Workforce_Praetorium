MODEL REQUIREMENT: This job runs on z-ai/glm-5.2 (GLM-5.2, medium reasoning). If re-creating, pin this model explicitly.

You are Marcus (Praetorium orchestrator). Capture a PRE-RUN snapshot of system state just before tonight's agent-proposal timer fires (04:30 Amsterdam). Write the snapshot to `~/logs/overnight/pre-snapshot-$(date -u +%Y-%m-%dT%H%M)Z.log` as plain text.

## What to capture (one section each)

1. **Header**: timestamp, hostname, uptime, current user
2. **MCP servers**: list each (hermes mcp list), note status
3. **Gateway health**: hermes gateway status, capture PID
4. **Kanban state**: `hermes kanban list --json` — dump all tasks with status, assignee, created/started/completed timestamps
5. **Inbox files**: `ls -la ~/agent-worktrees/inbox/_inbox/agents/` — capture filenames + mtimes (mtime is the authoritative signal)
6. **Cron jobs**: `python3 -c "import json; print(json.dumps(json.load(open('/home/dave/.hermes/cron/jobs.json'))['jobs'], indent=2))"` — list all scheduled jobs with their next_run_at + last_run_at
7. **Box clock sanity**: `timedatectl status` — confirm timezone matches Europe/Amsterdam
8. **Disk / system**: `df -h /home`, `free -h`

## Output format

Plain text markdown. Header block + each section with a clear `## <section>` header. Write to `~/logs/overnight/pre-snapshot-YYYY-MM-DDTHHhMMz.log`. After writing, `exit 0`. No delivery to Dave (this is a silent background log).

## Rules

- Read-only. Never mutate anything.
- If any command fails (non-zero exit), log the error in that section and continue — do not abort.
- No summarization, no analysis — raw state capture.

