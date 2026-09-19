# Claudius's five improvements, corrected — 2026-09-19

Claudius's scheduled research run (2026-09-18 23:30 CEST, receipt `buzz-agent@claudius`
21:30Z, 8 min, 6 Brave searches + 2 WebFetch through the bridge, artifact posted) proposed
five agent-config improvements. Dave: implement them, corrected where wrong; and keep the
`shared@jbuitenhuis` plugin for trajan, marcus and aurelian, who build or review software.

| # | Proposed | What was true | What landed |
|---|---|---|---|
| 1 | Fleet deny-list in `/etc/claude-code/managed-settings.json` | Right mechanism — a managed file survives any `--setting-sources`/`--settings`. Wrong scope — it binds Dave's interactive sessions and the nine scheduled runners too. | Managed file rendered from the base's **twelve credential-path rules only**; root-installed, drift-checked (eighth comparison). Fleet policy stays in the per-agent files. |
| 2 | Staleness watch: `claude-agent-acp` 0.64.0→0.79.0, `codex-acp` 1.1.9→1.12.0 | Correct, verified against npm. | `bin/adapter_versions.py`; `INFO` rows in `check-loaded.sh`; canary upgrade procedure in the runbook (aurelian first, gate 14 on his live child). The upgrade itself is step 10 below. |
| 3 | Ban literal `--private-key` argv; "caught a short-lived non-systemd buzz-acp passing it" | The evidence was his own shell: `pgrep -f buzz-acp` matched the `bash -c` whose command line contained both strings. All five `buzz-acp` take the key from env. **The real exposure was one level down**: every `claude` child's argv carried `BUZZ_PRIVATE_KEY` inside the adapter's `--mcp-config <json>` (10 of 10). | Wrapper files the JSON 0600 under `$XDG_RUNTIME_DIR/buzz-team/` and passes the path; launch script clears old files; gate 14 counts the key in every cgroup argv and reads the filed config's server names. |
| 4 | Harden `qmd-mcp`/`brave-mcp` (`ProtectHome`, `PrivateTmp`, `IPAddress*`) | `NoNewPrivileges` + `ProtectSystem=full` already there; both already bind loopback. `ProtectHome` impossible (both live under `/home/dave`), `IPAddress*` would cut brave's outbound, qmd needs `/dev/dri`. | The no-behaviour-change set; `systemd-analyze security` 8.7 EXPOSED → 3.6 / 3.3 OK (offline render; live after restart). Omissions named in the unit. |
| 5 | Per-agent Linux service accounts | Honest: named, not built, sized L. Collides with the broker's trust model, the shared memory pool, and `dave`-owned trees. | `design/open-decisions.md` W21 with the three preconditions; not built. |

Plus (Dave): `plugins = ["shared@jbuitenhuis"]` on the three coders' manifests →
`enabledPlugins` in their rendered settings. Measured before wiring: under
`--setting-sources=` the plugin's seven skills load and its SessionStart hook prints
`# Coding Standards`; under `--strict-mcp-config` its `context7`/`linear` servers do not.

## Measurements the design rests on (2026-09-19)

- `claude` child argv, claudius: `--mcp-config <json len=579 keys mcpServers/type/command/args/env contains_BUZZ_PRIVATE_KEY=True>` — ten children across marcus/claudius/trajan; no `buzz-acp`, `bwrap`, `codex`, bridge or aurelian process.
- The `claude` child is the ACP **session** (one per channel/DM), 10–11.5 h old, ~280 MB RSS each, 3.1 GB fleet-wide; `--idle-timeout 900` ends a silent turn, nothing evicts a session. (Corrects the 09-18 "lingers 11 min" reading; PR #57.)
- Plugin probe: `claude -p … --strict-mcp-config --setting-sources= --settings '{"enabledPlugins":{"shared@jbuitenhuis":true}}'` → `plugins: [shared@…/3badaf1d66a0]`, skills `shared:*` ×7, `mcp_servers: []`, transcript carries `SessionStart:startup hook success: # Coding Standards`.
- `CLAUDE_CODE_EXECUTABLE` is read by claude-agent-acp itself (`dist/acp-agent.js:230`, 0.64.0; bundled SDK 0.3.220) — the seam an adapter upgrade must keep.
- `/etc/claude-code/` did not exist. `qmd-mcp` runs `QMD_LLAMA_GPU=vulkan` with `render video` groups (drop-in `gpu.conf`).

## Landing

Branch `feat/claudius-five-corrected`, one PR. Deploy order after merge (step 9 of the plan):
`bin/deploy_buzz_team.sh` (wrapper, launch script, settings, check-loaded, verify-fleet — and
PR #58's `Skill(schedule)` deny, merged undeployed), `sudo install -D -o root -g root -m 0644
etc/claude-code/managed-settings.json /etc/claude-code/managed-settings.json`, `sudo cp` the
two MCP units + `daemon-reload` + restart them, restart the four Claude units when idle,
`check-loaded.sh`, `verify-fleet.sh`, `bin/verify.sh`. Then the canary upgrade (runbook
§ Harness versions), which needs a DM from Dave to aurelian.
