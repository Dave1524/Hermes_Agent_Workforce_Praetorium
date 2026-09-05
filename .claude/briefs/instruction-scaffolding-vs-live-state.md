# Brief: bring the instruction scaffolding back in line with the live box
**Date:** 2026-09-04   **Verify:** `bash bin/verify.sh` (repo root) for anything under
`~/dev/agent-workforce`; `~/.config/buzz-team/verify-fleet.sh` + `~/.config/buzz-agents/check-loaded.sh`
for anything at machine level. **Both gates, because this work spans both domains.**

## The problem, stated once

The instruction files are the only thing standing between an agent and a wrong action, and they are
the least-checked artifacts on the box. Nothing joins them to the state they describe. Measured
2026-09-04, every one of the findings below is a live disagreement between a file an agent loads and
the machine it loads on.

`~/CLAUDE.md` is **37,172 bytes last edited 2026-08-14 — 21 days stale**, and it is the file every
Claude Code session on this box reads first. `~/.codex/AGENTS.md` is the same date. The
*project* files have moved on (agent-workforce 09-02, boxsafe vault 09-02) while the machine-level
pair has not, so the most-loaded documents are the most out of date.

## Confirmed drift — each of these was measured today, not recalled

| # | File | Claim | Live state |
|---|---|---|---|
| 1 | `~/dev/agent-workforce/CLAUDE.md:45` | "**No canonical vault access.** This box holds no credential to the canonical `obsidian-ai-os` vault — only a repo-scoped deploy key to `obsidian-ai-os-boxsafe`." | **False.** `~/.ssh/config` maps `Host github-canonical` → `~/.config/agent-workforce/keys/canonical_deploy`; `git ls-remote` against `git@github-canonical:Dave1524/Obsidian_AI_Operating_System.git` authenticates and lists refs. `:120` cites this claim as settled. |
| 2 | `~/CLAUDE.md` throughout | a **four**-agent fleet ("all four agents here are `@`-addressable", "shared by all four agents") | **Five** `buzz-agent@*` units are `active running`: marcus, claudius, augustus, trajan, **aurelian**. |
| 3 | `~/CLAUDE.md:110` | qmd-mcp serves "494 documents as of 2026-08-13" | Four different numbers are in play: doc **494**, the MCP server's start-time blurb **498**, `fleet_eval` index-freshness **528**, files on disk **532**. The blurb being a snapshot is *already documented* at `:126`; the doc's own figure has the same defect and says so about nobody. |
| 4 | `~/CLAUDE.md` § MCP surfaces | "Claude Code additionally has `brave-search` …, `HA` (project scope, HTTP + bearer), and the claude.ai OAuth connectors (Figma, Gmail, Drive, M365, **Notion**) plus plugin servers (context7, **linear**)" | `claude mcp list` shows no `HA` from this cwd (project scope — establish which project, do not assert absence); `plugin:shared:linear` reports **"Needs authentication"**, i.e. listed and unusable. |
| 5 | `~/CLAUDE.md` § MCP surfaces | "the Notion connector is listed but **must not be used**" — prose | `~/.claude/settings.json` `permissions.deny` now carries `mcp__claude_ai_Notion`, so the schema is withheld and no Notion tool is reachable. The doc describes a rule you keep; reality is a rule kept for you. Same distinction the vault-push section draws — apply it here. |
| 6 | `~/CLAUDE.md:86-87` | "codex-cli 0.146.0"; permission profiles "verified 2026-08-04" with a four-path deny profile | Installed is **codex-cli 0.147.0**. `~/.codex/config.toml` has `approval_policy = "never"`, `sandbox_mode = "workspace-write"` and **no `default_permissions` key at all** — so the profile the doc describes at length is *not active*, and Codex still reads `.ssh`, `.config/agent-workforce` and `.config/buzz-agents` freely. The doc reads as though the fix landed. |
| 7 | box convention | "each project has its own top-level `CLAUDE.md`" and every `AGENTS.md` is a thin pointer beside it | `~/dev/energy-ledger/` has `CLAUDE.md` and **no `AGENTS.md`** — Codex runs there with no project instructions at all. The other three projects have both. |
| 8 | `~/dev/agent-workforce/CLAUDE.md` § Roster | four Hermes profiles, Marcus "was + kanban owner; S3 retired 2026-09-02" | Roster still frames the fleet as the Hermes profiles and does not mention aurelian at all. Reconcile with #2 and decide which file owns the roster — today both describe it and neither is authoritative. |

## Acceptance criteria

1. Every row above is either corrected in the file named, or explicitly recorded as
   deliberate-and-unchanged with the date it was re-confirmed. No row is silently dropped.
2. Row 1 is corrected in **both** places (`:45` and `:120`) and states the real constraint: the box
   *can* write canonical — the `pre-push` guard's own header says "This is friction and a record, not
   a boundary" — so `agents/*` branches are **a rule you keep**, phrased the way `~/CLAUDE.md`
   already phrases the identical situation for `main`.
3. Row 6 does not leave a reader believing the Codex deny profile is in force. Either state plainly
   that it is available-but-unconfigured, or configure it — **but configuring it is a separate
   decision and out of scope here** (see below).
4. Row 3 is fixed by *removing the bare number*, not by writing a fresher one. A count in prose is
   stale the day after it is written; if a figure is kept it carries a `MEASURED <date>` marker that
   the next writer overwrites, per the `memory-edits-replace-dont-append` rule.
5. `~/dev/energy-ledger/AGENTS.md` exists and is a thin pointer to its sibling `CLAUDE.md`, matching
   the shape of the other three.
6. Both gates green: `bash bin/verify.sh` and `~/.config/buzz-team/verify-fleet.sh`
   + `~/.config/buzz-agents/check-loaded.sh`.

## Files to modify

- `~/CLAUDE.md` — rows 2, 3, 4, 5, 6. The largest edit. Fleet size, qmd count, MCP surface table,
  Notion prose→mechanism, Codex version and the profile's *actual* status.
- `~/.codex/AGENTS.md` — mirror any change to the "Out of scope — do not read" list (the file's own
  rule: "Change one, change both"), and re-confirm it is still a thin pointer rather than a fork.
- `~/dev/agent-workforce/CLAUDE.md` — rows 1 (lines 45-46 and 120) and 8 (Roster).
- `~/dev/agent-workforce/AGENTS.md` — 2,743 bytes, **last touched 2026-08-03, the oldest instruction
  file on the box**. Confirm it is still a pointer and has not re-forked; that regression is exactly
  what the 08-03 rewrite fixed.

## Files to create

- `~/dev/energy-ledger/AGENTS.md` — thin pointer to `~/dev/energy-ledger/CLAUDE.md` plus
  Codex-specific mechanics only. Copy the shape from `~/dev/AI_Trading_Bot/AGENTS.md`.
- `tests/test_instruction_scaffolding.sh` — see Test plan.

## Test plan

The point is to leave behind a **join**, not just corrected prose. Every finding above survived
because nothing compares these files to anything. Two of the eight are mechanisable cheaply; the rest
are prose and are not, and the suite should say so rather than implying coverage it lacks.

New suite `tests/test_instruction_scaffolding.sh` (tests/, **not** `bin/` — no deploy coupling, no
drift, and it needs no runtime counterpart):

1. Canary: `yes | grep -q y`, per the repo's `pipefail`-in-a-condition rule.
2. **Coverage, both directions:** every `~/dev/*/CLAUDE.md` has a sibling `AGENTS.md`, and every
   `AGENTS.md` has a sibling `CLAUDE.md`. Catches row 7 and its mirror.
3. **Thin-pointer invariant:** each `AGENTS.md` names its sibling `CLAUDE.md`, and is materially
   smaller than it. Pick the ratio from measured values, not a guess — agent-workforce is 2.7 KB
   against 13.6 KB today. This is the check that would have caught the pre-2026-08-03 forks, where
   `AI_Trading_Bot/AGENTS.md` had lost both HARD safety sections.
4. **Fixtures first, live tree second** — same shape as `tests/test_memory_index_budget.sh` shipped
   today. Build a synthetic tree missing an `AGENTS.md` and prove the check fails; build a fork-shaped
   one and prove the ratio assertion fails; build a healthy one and prove it passes. Without this the
   live assertions are a check that cannot fail.
5. `box_only_with` guards anything reading `~/dev/*` outside this repo, and the resulting `SKIP:` line
   is added to `tests/ci-expected-skips.txt` **in the same commit**, with that file's header count
   updated — it currently declares eight.

Explicitly NOT asserted, and the suite header must say so: freshness of prose, correctness of a
document count, whether a described mechanism is configured. Those are the other six rows and no
cheap check covers them.

## Out of scope / do not touch

- **Configuring the Codex permission profile.** Row 6 is a documentation fix here. Turning the
  profile on changes the box's security posture and the `bwrap` mount namespace — `~/CLAUDE.md`
  records two syntax traps that make a wrong profile unable to exec `codex` at all. Separate brief,
  separate decision, Dave's call.
- **`~/.config/buzz-agents/**` — the per-agent `.prompt` files and `GUARDRAILS.md`.** Deny-listed;
  no agent can read or verify them. If a guardrail wording change implies a prompt re-sync, say so and
  stop — running `check-loaded.sh` afterwards is Dave's step.
- **Vault content.** `~/dev/Obsidian_AI_Operating_System` is a canonical clone whose local
  `00_system/CLAUDE.md` (2026-08-17) is **behind** the published mirror's (2026-09-02) — the mirror
  describes a role-aware hook installer the clone does not. `git fetch` before reading either, or a
  review will "correct" newer text with older text. Vault edits go on `agents/<date>-<slug>` branches
  and are Mac-merged; do not push `main`, and never reach for `--no-verify`.
- **`~/.claude/briefs/`** at box root — a stale leftover (`current.md`, `augustus-codex-harness.md`).
  Not this brief's job; the real briefs live in `<project>/.claude/briefs/`.
- Roster *policy*. Row 8 asks which file owns the roster, not that the roster change.

## Notes / preconditions

- **Read before writing, in every case.** Six of the eight rows are wrong in the direction of
  describing a fix that did not land or a constraint that no longer holds — the failure mode is a
  confident document, not a blank one. Verify each against the live box the way this brief did
  (`systemctl --user list-units 'buzz-agent@*'`, `claude mcp list`, `codex --version`,
  `git ls-remote`), and put the command in the file where a number would otherwise rot.
- The canonical-vault correction (row 1) is the one with teeth: an agent that believes the box has no
  canonical credential will not think to be careful with one it actually has.
- `agent-workforce-auto-sync.timer` fires every 15 minutes and pushes any dirty tree in
  `~/dev/agent-workforce` under a generic message. Branch **in a worktree**, never in the canonical
  checkout — a checkout left off `main` makes the unit fail and pages Dave (it did today).
- Changes to `~/CLAUDE.md` and `~/.codex/AGENTS.md` are **not** in any repo and have no auto-sync,
  no PR and no review. They are the highest-leverage and least-recoverable edits in this brief;
  copy each file before editing.
- Stage by explicit path, never `git add -A`. The repo is public — no key material, and the key
  *paths* named above are already public in `~/CLAUDE.md`, so naming them is not a new disclosure.
