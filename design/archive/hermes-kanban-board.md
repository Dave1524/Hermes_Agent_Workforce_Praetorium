# S3 — the hermes kanban board, retired 2026-09-02

Content-free record of what the board held, taken with `hermes kanban list --json`
on 2026-09-02 while `hermes-gateway.service` was still `active`+`enabled`, per
brief 5 criterion 2 and `open-decisions.md` D7 step 2.

**This file carries no card content, and that is deliberate.** This repo
(`Dave1524/Hermes_Agent_Workforce_Praetorium`) is **public** — verified 2026-09-02 by an
unauthenticated `GET /repos/...` returning 200 with `"private": false` — and
`agent-workforce-auto-sync.timer` pushes any dirty tree to it within 15 minutes. The 11
cards carry 36,800 bytes of titles, bodies and client-derived detail. That full record
lives at `~/OUTBOX/hermes-kanban-full-export-2026-09-02.{json,md}`, outside every git
repo on this box. D7 step 2 named `design/archive/` as the destination and was right
about durability; it did not ask the boundary question, and taken literally it publishes
client content. Split, not overridden.

## What S3 ever did

| | |
|---|---|
| Cards, lifetime | **11** |
| Status | 6 `done`, 5 `blocked` |
| Assignees | trajan 5, augustus 4, claudius 2 |
| First card | 2026-07-10 07:30:36 UTC |
| Last card created | 2026-07-20 02:34:36 UTC |
| Last completion | 2026-07-20 02:39:47 UTC |
| Idle at retirement | 44 days |
| Cards ever dispatched | 6 of 11 (the 5 `blocked` have no `started_at`) |
| Cards with a non-empty `skills` field | **0 of 11** |
| `done` cards carrying a `result` | **0 of 6** |
| Board field populated | none — all 11 have `board = null` |

## The two measurements that settled the decision

**`skills` was never used once.** Every card's `skills` field is `[]`. The per-profile
allowlist machinery (`bin/apply_skills_allowlist.sh`, `docs/skills_allowlist.md`,
`~/.hermes/shared-skills/`) was built for a surface that never exercised it from a single
card. This answers `agent-model.md` §8 decision 4(c) by fact rather than preference — for
the *offering* question only. It is **not** licence to delete the allowlist script: it
writes `~/.hermes/profiles/<p>/config.yaml`, which the live `local-tier-eval` job still
reads six times a day.

**The 5 `blocked` cards were never dispatched at all.** They are the `vpc-seo` work,
blocked since 2026-07-10 and assigned to `engineer` — a profile that is not on disk
(`workflow-registry.md:131-134`). They were not stalled work; they were work the board
could not route. Dave moved them into Notion before this retirement (confirmed
2026-09-02); the full bodies are also in the OUTBOX record above as a backstop.

## What was retired, and what was not

Retired: the board, `hermes-gateway.service` (disabled + stopped, unit file kept on disk
for one review cycle per D7 step 3), `bin/kanban_run_and_wait.sh` and its two suites, and
the hermes cron host the gateway carried.

**Not retired, and load-bearing:** `~/.local/bin/hermes` (the CLI) and
`~/.hermes/profiles/`. `bin/local_tier_eval.sh:105` execs the CLI as
`"$HERMES" -t "$toolset" -z "$prompt" -p marcus -m "$model"`, and `-p marcus` names a
hermes profile directory. Verified 2026-09-02, immediately after the gateway stopped:
that exact invocation returns exit 0 and the expected output. The board never needed the
gateway either — `hermes kanban list --json` still returns all 11 cards with it down.

## One trap for whoever reviews the gateway

**Stopping it lands it in `failed`, not `inactive`, and that is the gateway's own bug.**
It exits 1 on SIGTERM (and prints its startup banner on the way out). The correct end
state needs `systemctl --user reset-failed hermes-gateway.service` after the stop, which
this retirement ran. Without it a retired unit sits in `systemctl --user --failed`
forever and trains its reader to skip the one command that answers "what is wrong".
