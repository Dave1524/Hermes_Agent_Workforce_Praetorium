# NUC-42 — Per-profile skills allowlist (prompt trim)

## Problem

Every Hermes profile (`claudius`, `augustus`, `trajan`, `marcus`) set
`skills.external_dirs: [~/.hermes/shared-skills]`, so each one indexed the **entire**
shared tree — **147 external `SKILL.md`s / ~6.0 MB on disk** — plus its ~65 local
skills. The single biggest offender is `shared-skills/plugin-finservices` (**65
skills**), which no profile on this box uses, followed by `resume` (20) and
`project-skills` (1). The rendered `<available_skills>` preamble is prepended to
the system prompt on **every** turn of **every** session, so this is pure fixed
overhead on latency and (for cached-preamble models) cost.

## Fix

Two OFFER-time filters, applied per profile in `~/.hermes/profiles/<p>/config.yaml`.
**Nothing is deleted** — every skill stays loadable via `skill_view(name)` /
`--skills`; only the always-on index shrinks.

1. **`skills.external_dirs`** → a role-scoped list of shared-skills **subdirectories**
   instead of the whole tree. `iter_skill_index_files` walks each dir recursively,
   so subdir entries index only the skills under them. This is what drops the
   65-skill `plugin-finservices` tree (plus `resume`, `project-skills`) from every
   profile — the biggest win.
2. **`skills.disabled`** → a denylist of LOCAL per-profile skill **frontmatter
   names** that `external_dirs` subsetting can't reach (the local `~/.hermes/
   profiles/<p>/skills/` tree). Matched by `frontmatter_name`/`skill_name`, not
   category (`build_skills_system_prompt` in `agent/prompt_builder.py`).

The live shared-skills tree and local skills dirs are **not touched** — the gateway
reads them and the code flags agent-created skills as project memory. Subsetting is
config-only and fully reversible.

## Per-role subsets

| Profile   | Role                    | `external_dirs` (shared-skills subdirs)            | external skills |
|-----------|-------------------------|----------------------------------------------------|-----------------|
| claudius  | research analyst        | `plugin-qmd`, `vault-business`, `plugin-shared`    | 2 + 15 + 7 = 24 |
| augustus  | content / vault ops     | `vault-business`, `plugin-shared`                  | 15 + 7 = 22     |
| trajan    | executor engineer       | `plugin-official`, `plugin-shared`, `anthropic-generic` | 23 + 7 + 14 = 44 |
| marcus    | orchestrator / gov      | `plugin-shared`, `vault-business`, `plugin-official` | 7 + 15 + 23 = 45 |

Local `skills.disabled` per profile (frontmatter names; nothing deleted):

- **claudius** — keeps `research/*`, `data-science`, `note-taking`, `creative`,
  `software-development`, `autonomous-ai-agents`. Disables: `apple-*` (macOS, already
  platform-filtered on Linux — listed for hygiene), `computer-use`, `openhue`,
  `xurl`, all `media` (`gif-search`, `heartmula`, `songsee`, `youtube-content`), all
  `github/*`, all `mlops/*`, plus `petdex`/`yuanbao`/`dogfood`.
- **augustus** — keeps `creative`, `research`, `productivity`, `software-development`,
  `vault-business`, `autonomous-ai-agents`, `youtube-content`. Disables `apple-*`,
  `computer-use`, `openhue`, `xurl`, all `mlops/*`, `gif-search`/`heartmula`/`songsee`,
  `petdex`/`yuanbao`/`dogfood`.
- **trajan** — keeps `github/*`, `software-development`, `computer-use`,
  `data-science`, `autonomous-ai-agents`. Disables `apple-*`, `openhue`, `xurl`, all
  `media`, all `mlops/*`, `petdex`/`yuanbao`/`dogfood`.
- **marcus** — same denylist as trajan plus `computer-use` (keeps `governance`,
  `github/*`, `software-development`, `vault-business`).

## Before / after (measured on-box, read-only)

Measured by replicating `build_skills_system_prompt`'s index-render logic (Linux
platform filter applied; most `SKILL.md`s carry empty descriptions, so the block is
mostly names). These are the **expected** trimmed sizes; the authoritative re-measure
happens after the gateway restart regenerates `.skills_prompt_snapshot.json`.

| Profile   | `<available_skills>` bytes (before → after) | reduction | external-only bytes (before → after) | external reduction |
|-----------|---------------------------------------------|-----------|--------------------------------------|--------------------|
| claudius  | 17,897 → 5,756                              | 67.8%     | 12,605 → 2,419                       | **80.8%**          |
| augustus  | 18,623 → 6,902                              | 62.9%     | 12,605 → 2,253                       | 82.1%              |
| trajan    | 17,897 → 8,441                              | 52.8%     | 12,605 → 4,519                       | 64.1%              |
| marcus    | 18,002 → 8,546                              | 52.5%     | 12,605 → 4,618                       | 63.4%              |

Skills listed drops from ~212 to ~66 (claudius). External `plugin-finservices` (65
skills) is absent from all four; `resume` (20) and `project-skills` (1) are gone too.

### Acceptance spot-checks (claudius, post-change index)

- No `plugin-finservices` skill present (e.g. `kyc-aml` absent). External count 24.
- Role-critical retained: `qmd`, `release` (plugin-qmd); `investment-research`,
  `eod-wrap`, `vp-pitch-deck`, `linkedin-content-engine` (vault-business); `arxiv`,
  `llm-wiki` (local research); `obsidian` (note-taking).
- Disabled-but-loadable: `xurl`, `github-issues` absent from the index yet still
  resolvable via `skill_view("xurl")` (nothing deleted from disk).
- trajan keeps local `software-development` (`plan`, `spike`, …) + `plugin-official`
  (`pdf`, `docx`, `pptx`, `xlsx`, `mcp-*`, …). augustus/marcus keep `vault-business`.

## How to apply (live steps — run by Dave at the gate)

The repo ships `bin/apply_skills_allowlist.sh`. It is idempotent (re-run = no-op once
applied) and reversible (writes a `config.yaml.bak-skills-allowlist-<stamp>` before any
edit; restore by copying it back). It uses the hermes venv's `ruamel.yaml` for a
comment-preserving round-trip, so the rest of each config is untouched. It does **not**
restart the gateway or delete snapshots — those are separate steps below.

```
# 1. Apply the config edits (backs up each config first):
bash ~/agent-workforce/bin/apply_skills_allowlist.sh   # or from ~/dev/agent-workforce

# 2. Force a rebuild — delete stale snapshots (they key off the LOCAL skills_dir
#    manifest only, so an external_dirs change does NOT auto-invalidate them):
rm -f ~/.hermes/profiles/{claudius,augustus,trajan,marcus}/.skills_prompt_snapshot.json

# 3. Restart the gateway to clear the per-process external-dirs LRU cache
#    (interactive/Discord sessions). Cron oneshots spawn fresh and pick it up:
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user restart hermes-gateway

# 4. Verify: no errors, snapshots regenerate, index is trimmed:
journalctl --user -u hermes-gateway -n 50 --no-pager
```

To revert a single profile: `cp ~/.hermes/profiles/<p>/config.yaml.bak-skills-allowlist-<stamp> ~/.hermes/profiles/<p>/config.yaml`, then repeat steps 2–3.
