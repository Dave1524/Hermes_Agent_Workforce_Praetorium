# Per-job override env files

These files are **non-secret task wiring**. They live at runtime under
`~/.config/agent-workforce/*.env` and are pointed at by systemd via
`Environment=AGENT_JOB_OVERRIDES=…`.

`agent_propose.sh` sources the canonical `secrets.env` first, then the override
file — so overrides may set `AGENT_PROFILE` / `AGENT_TASK_SLUG` / `AGENT_RUNTIME_CMD`
only. Never put API keys here.

## Install

```bash
# From a checkout of this repo:
install -m 600 config/job-overrides/augustus-content.env.example \
  ~/.config/agent-workforce/augustus-content.env
# edit paths if your deploy root is not ~/agent-workforce
```

See `docs/runbook.md` § Job wiring for the full map.
