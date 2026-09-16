# The hermes persona profiles, retired 2026-09-14 (T6.1)

Record of the four persona profiles under `~/.hermes/profiles/` as of their deletion, and of
what the repo stopped doing with them. The brief is `.claude/briefs/t6-1-hermes-residue.md`;
the gate is `tests/test_hermes_residue.sh`. Content-free, like `hermes-kanban-board.md` beside
it: this repo is public and auto-synced, so store contents and session files stay in the
tarball named below, outside every git repo on this box.

## What the profiles were

MEASURED 2026-09-14, read-only, before any step of T6.1 ran.

| Profile | Model | Skills offered | Notes |
|---|---|---|---|
| marcus | `deepseek/deepseek-v4-flash` | 46 (plugin-shared 7 + vault-business 16 + plugin-official 23) | `max_turns` 24; carried the `local` / `local-big` alias block that `local-tier-eval` ran on (`-p marcus -m local`) |
| claudius | `anthropic/claude-sonnet-5` | 25 (plugin-qmd 2 + vault-business 16 + plugin-shared 7) | the only profile granted plugin-qmd; the episodic store the scheduled jobs wrote (`AGENT_OWNER=claudius`) |
| augustus | `openai/gpt-5.5` | 23 (vault-business 16 + plugin-shared 7) | no ZDR provider pin — **D4** |
| trajan | `deepseek/deepseek-v4-flash` | 44 (plugin-official 23 + plugin-shared 7 + anthropic-generic 14) | owned the `vpc-seo` kanban board until D7 |

Skill counts are the 2026-09-01 measurement from `design/agent-model.md` §2: the index was
148 `SKILL.md` across nine `~/.hermes/shared-skills/` subdirectories with `skills.external_dirs`
+ `skills.disabled` applied per profile, and the two lists were disjoint — `disabled` removed
zero of the allowlisted skills on every profile (it suppressed Hermes's bundled set:
`apple-notes`, `imessage`, `computer-use` and friends), so the offer was exactly the
`external_dirs` total.

Directory sizes: marcus 165M, augustus 70M, claudius 60M, trajan 37M — `auth.json`, `state.db`,
`sessions/`, config backups. No key-named field in any `config.yaml`.

## The episodic stores

`~/.hermes/profiles/<p>/memories/MEMORY.md` (NUC-21). Last writes: augustus 2026-09-11,
claudius 2026-09-11, marcus 2026-09-09, trajan 2026-07-20.

What wrote them: `bin/agent_propose.sh`'s post-run memory block, one line per run, keyed by
`AGENT_OWNER` — retired at T6.1 step 4 (`memory=na` on every run; the per-run record is the
receipt, `bin/workflow_receipt.py`).

What read them: nothing but `bin/bd_stall_radar_kernel.py`'s three-day dedup, rerouted at T6.1
step 3 to `~/agent-workforce/var/bd-stall-radar/flagged.jsonl`, a repo-owned JSONL state file.
`bin/consolidate_memory.sh` on `memory-consolidation.timer` pruned them nightly — a pruner whose
input is retired is retired with it (contract at `design/archive/contracts/memory-consolidation.md`,
units at `systemd/archive/`).

## The skills allowlist

`bin/apply_skills_allowlist.sh` (NUC-42) wrote `skills.external_dirs` into each persona
`config.yaml`; `docs/skills_allowlist.md` documented it. It governed only S3, the kanban
dispatch surface, and the retirement of that surface measured what it was worth: **0 of the
board's 11 cards ever set a non-empty `skills` field** (`hermes-kanban-board.md`). After D7 it
survived on one reader, `bin/local_tier_eval.sh` running `hermes -p marcus`; T6.1 moved that
runner to `base0`, which has no skill index, and deleted both files. Whether the allowlist ever
affected a `-z` oneshot was never measured.

## The kanban board (trajan's `vpc-seo`), for the record

Retired 2026-09-02 (D7). Its 5 SEO cards were assigned to `engineer`, a profile not on disk, so
they could never dispatch — no `started_at` on any of them, ever. Reassigned to trajan
2026-09-01, left `blocked` on purpose, then moved to Notion by Dave before the retirement. Full
card bodies: `~/OUTBOX/hermes-kanban-full-export-2026-09-02.md` (outside every repo).

## What remains under `~/.hermes/profiles/`

`base0`, `leantest` (Tier 0, `qwen3-64k` on Ollama) and `default`. base0 carries the `local` /
`local-big` alias block from land-time step 6; `local-tier-eval` runs `-p base0`. The `hermes`
CLI and venv stay: `bin/deliver.sh`'s Discord leg execs them until the Discord cutover, and
`local-tier-eval` execs them for the local tier (both allowlisted `live` in
`tests/fixtures/hermes-residue/allowlist.tsv`).

## Land record

- Backup tarball: `~/OUTBOX/hermes-profiles-retired-2026-09-16.tgz` (mode 600, 88 MB; marcus,
  claudius, trajan, augustus — outside every repo). Restore is `tar xzf … -C ~/.hermes/profiles`.
- `ls ~/.hermes/profiles/` after land: `base0 default leantest` (MEASURED 2026-09-16).
- **D4: closed 2026-09-16 — deleted.** Dave's call: the profile was read by nothing after T6.1,
  and the live augustus (`buzz-agent@augustus`, codex-acp) never read it; a pin would have
  guarded a file no runtime execs.
