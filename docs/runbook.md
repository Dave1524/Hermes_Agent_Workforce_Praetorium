# Praetorium runbook — backup, restore, rebuild (NUC-19)

## What must be backed up (inventory)

| Asset | Where | Backup path |
|---|---|---|
| Service units | `/etc/systemd/system/{qmd-mcp,qmd-refresh,agent-proposal}*` | `backup_config.sh` tarball |
| Scripts & docs | `~/agent-workforce/{bin,docs,profiles}` | `backup_config.sh` tarball |
| qmd config | `~/.config/qmd/index.yml` | `backup_config.sh` tarball |
| Secrets template | `~/.config/agent-workforce/.env.example` + README | `backup_config.sh` tarball |
| Hermes profiles | `~/.hermes/profiles/` (SOUL.md, config.yaml — no .env) | add on first profile change |
| Secrets values | `secrets.env`, deploy key | **NEVER backed up** — re-issued at providers (see `~/.config/agent-workforce/README.md`) |
| Vault content | GitHub `Dave1524/obsidian-ai-os-boxsafe` | already remote; clone is disposable |
| qmd index/embeddings | `~/.cache/qmd` | disposable — rebuilt by `qmd update && qmd embed` |

Run `~/agent-workforce/bin/backup_config.sh`, then pull the tarball to the Mac:
`scp praetorium:~/agent-workforce/backups/<latest>.tar.gz ~/backups/praetorium/`

## Rebuild checklist (fresh Ubuntu → working box)

1. Install Ubuntu Server LTS headless; create user `dave`; enable SSH (NUC-02/03 pattern).
2. Join Tailscale (`tailscale up`), confirm Mac SSH; UFW default-deny + 22/tcp (Tailscale-only net).
3. `sudo apt install git curl xz-utils nodejs npm && sudo npm i -g @tobilu/qmd`.
4. Install Hermes: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser`.
5. Restore the config tarball over `$HOME` and `/etc/systemd/system/` (or rsync from this repo of scripts).
6. Recreate secrets per `~/.config/agent-workforce/README.md` (new deploy key → register on repo,
   new OpenRouter key → re-apply spend cap, new Discord token).
7. `~/agent-workforce/bin/finish_boxsafe_clone.sh` (clone, index, exclusion gates, enable services).
8. Verify: `~/agent-workforce/bin/praetorium-status.sh` — all green; run `llm_smoke_test.sh`.

## Restore-path test log

- 2026-07-06: config tarball created, extracted to a scratch dir, and diffed against live files —
  restore path verified (see NUC-19 card for the transcript reference).
