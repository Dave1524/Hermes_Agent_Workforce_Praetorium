# Brief: T3.2 — `skills = [...]` on all 33 workflow entries, joined to what the run is offered
**Date:** 2026-09-11   **Verify:** `bash bin/verify.sh` from the repo root

Source of scope: `docs/dev-plan-2026-09.md:235-239` (T3.2, phase "3 Skills", size M; Notion card
`3d48d768-1ede-8131-9758-4cb9808ac1e`, Gate: "join green, 33 of 33 carry the field"). Blockers
both landed: T3.1 `a83792a` (pointer tree + `--plugin-dir` wiring), T1.2 (runner join in
`tests/test_workflow_coverage.py`). Allocation source (frozen):
`design/archive/open-decisions-closed-2026-09-07.md:330-360`.

**Definition of the field — decided here, not open.** `skills` on a `[[workflows]]` entry is the
sorted list of pointer-skill names under `skills/<owner>/skills/` that **the entry's mechanism
delivers to the run**. Not "skills this job might read", not "skills the profile mentions" — what
the runtime is handed. It is joined by **equality** to a mechanically derived offer, T1.2-style
(`got != want` → PROBLEM), and the join counts what it checked (D6 vacuity guard). Two mechanisms:

| `skills_mechanism` | offer = | applies to |
|---|---|---|
| absent (default, "plugin-dir") | the pointer names in the tree that the runner's `--plugin-dir` **default** resolves to; no runner file or no `--plugin-dir` ⇒ `[]` | every entry except the two below |
| `"heading-extraction"` | the `08_skills/<name>/SKILL.md` targets of every `bin/skill_sections.sh` invocation in the entry's `profile` | `augustus-content`, `content-change-dispatch` |

Universe for both: the repo's `skills/` tree (T3.1). The join reads the **declared** default
(`${PRAETORIUM_SKILLS_DIR:-$HOME/agent-workforce/skills/<owner>}`), exactly as the T1.2 join reads
`--model`/`--allowedTools` — a runtime override is out of the manifest's jurisdiction.

## Acceptance criteria

1. Every one of the 33 `[[workflows]]` entries in `design/agents/{augustus,aurelian,claudius,marcus,trajan}.toml`
   carries `skills = [...]` as a TOML array of strings; the empty list is written `skills = []`
   explicitly. A missing field is a PROBLEM, never a default.
2. Values, from the measured state (10 plugin-dir entries, 2 heading-extraction, 21 empty):
   - claudius `knowledge-digest`, `agent-proposal`, `raw-ingest`, `m1-signal-scan`,
     `bd-stall-radar`, `bd-followup-drafts` → `["investment-research", "meeting-prep", "prospect-research"]`
   - marcus `praetorium-daily-plan`, `overnight-morning-report`, `praetorium-eod-summary`,
     `weekly-pre-assembly` → `["agent-inbox-sync", "post-call-capture", "weekly-review"]`
   - augustus `augustus-content`, `content-change-dispatch` → `["linkedin-content-engine"]`, plus
     `skills_mechanism = "heading-extraction"` and `profile = "profiles/augustus_content_task.md"`
   - the five `buzz-agent@*` interactive entries and all 16 trajan platform entries (14 standing +
     2 spent) → `skills = []`
3. `tests/test_workflow_coverage.py` gains a **skills join** that, for every parsed entry,
   derives the offer per the table above and compares it to the declaration; ships four new
   assertion ids, each `PROBLEM\t<id>\t<detail>` on failure:
   - `skills-declared` — field present and a list of strings; duplicates are a PROBLEM.
   - `skills-mechanism` — `skills_mechanism`, when present, is `"heading-extraction"`; that value
     requires a `profile` inside the repo whose `skill_sections.sh` invocations name ≥ 1 vault skill,
     and every named skill must exist as `skills/<owner>/skills/<name>/SKILL.md`. Any other value,
     or heading-extraction with no profile / zero extractions / a name absent from the owner's
     tree, is a PROBLEM.
   - `skills-join` — `sorted(declared) != offered` → PROBLEM naming unit, owner, both lists.
   - `skills-join-counted` — the report prints
     `  skills join: checked N of M entries, K heading-extraction, J with a non-empty offer` and
     the SUMMARY line gains `skills_checked=N skills_he=K skills_offered=J`; `tests/test_workflow_coverage.sh`
     asserts N = M = `entries_summary` = `live_entries` (the `grep -c '^\[\[workflows\]\]'` count),
     N > 0, and K equals `grep -c '^skills_mechanism *= *"heading-extraction"'` over
     `design/agents/*.toml` and K > 0 — so the heading-extraction branch is proven exercised, not
     merely present.
4. `tests/test_workflow_coverage.sh` anchors all four ids (`check <id>` / `# (::id)`), and
   `design/fleet-suites.toml` declares them in the coverage suite's `asserts` list — W9
   `asserts-anchored` is red until both sides agree.
5. Negative controls: with the repo untouched the join is green (33 of 33, 2 heading-extraction,
   12 non-empty). The `.sh` suite proves the join bites with **temporary fixtures** (mktemp copies of
   the manifests, `DESIGN_AGENTS`-style override if the `.py` already takes one; otherwise a
   copied checkout under mktemp) for at least: (a) one entry with `skills` removed → `skills-declared`;
   (b) a claudius entry declaring `["meeting-prep"]` only → `skills-join`; (c) `skills_mechanism =
   "heading-extraction"` on an entry with no `profile` → `skills-mechanism`; (d) a trajan entry
   declaring `["systematic-debugging"]` → `skills-join` (an unreachable tree cannot be declared
   as delivered). Follow the fixture pattern already used for `runner-tools` in that file.
6. `design/agent-model.md` records the allocation as a **bet**, in numbers: 13 pointers; 7 offered
   on at least one live entry (6 by `--plugin-dir` across 10 entries, 1 by heading-extraction across
   2 entries); **1 of 13 named by any live workflow's profile** (`linkedin-content-engine`); 6 reach
   nobody (trajan's 4, augustus's `linkedin-review` and `blog-engine`). Whether the 6 plugin-dir
   offers are ever *invoked* is unmeasured until T3.3. §4 schema block documents `skills` and
   `skills_mechanism` on `[[workflows]]`; decision 4 (§8, "Skills posture") gets a dated line
   saying (b) is now declared per entry and joined, and what remains open is invocation evidence.
7. `profile-owner-header` (`tests/test_fleet_ownership.sh`) stays green: `profiles/augustus_content_task.md`
   line 1 becomes `Owner: augustus — ...` in the shape of `profiles/knowledge_digest_cc_task.md:1`;
   the existing task line becomes line 2. `tests/test_content_skill_extract.sh` still passes (its
   awk parser keys on the extractor call, not line 1).
8. Gate green after `bin/deploy` — `profiles/`, `docs/`, `skills/README.md` are drift-checked
   content trees, so the gate **cannot** be green on a branch that edits them until the deployed
   tree matches. Order: edit → `bin/deploy --dry-run` → `bin/deploy` → `bash bin/verify.sh` →
   commit → push by hand.
9. `docs/dev-plan-2026-09.md` T3.2 row gains a `**DONE <date>, <sha>.**` paragraph in T3.1's style
   (line 230) carrying the bet numbers; execution-order item 8 and the "Startable today" line
   (`:589`, `:594`) drop T3.2. `skills/README.md:66-71` is rewritten to say what is now declared
   rather than what T3.2 "will join"; keep "do not close the gap by inventing a runner".

## Files to modify

- `design/agents/claudius.toml` — `skills = [...]` on 7 entries (6 scheduled: the claudius triple; `buzz-agent@claudius`: `[]`). Place it after `suite`, before `notes`.
- `design/agents/marcus.toml` — 5 entries (4 scheduled: the marcus triple; `buzz-agent@marcus`: `[]`).
- `design/agents/trajan.toml` — 17 entries, all `skills = []` (16 platform incl. the 2 `spent`, plus `buzz-agent@trajan`). Do **not** touch `[surfaces.kanban] skills = 25` — different key, different table, retired surface.
- `design/agents/augustus.toml` — `augustus-content` and `content-change-dispatch`: add `profile = "profiles/augustus_content_task.md"`, `skills_mechanism = "heading-extraction"`, `skills = ["linkedin-content-engine"]`; `buzz-agent@augustus`: `skills = []`. `content-change-dispatch` reaches the same profile through `agent_propose.sh -> run_content_via_buzz.sh` (`CONTENT_TASK_PROFILE` default, `bin/run_content_via_buzz.sh:37`); say so in its `notes`.
- `design/agents/aurelian.toml` — `buzz-agent@aurelian`: `skills = []`.
- `tests/test_workflow_coverage.py` — the skills join. Concretely: (1) a `plugin_dir_tree(path)` that scans uncommented lines for `--plugin-dir\s+(\S+)`, peels and resolves the token through the same `assigns` map `parse_claude_flags` builds (`"$SKILLS_DIR"` → `assigns["SKILLS_DIR"]` = `$HOME/agent-workforce/skills/claudius`), and maps a `$HOME/agent-workforce/` or `~/agent-workforce/` prefix onto `ROOT`; factor the `assigns` collection into a helper both parsers call rather than duplicating the loop. Keep `parse_claude_flags`'s `None` short-circuit as is — the runner join's skip semantics must not change. (2) `pointer_names(tree)` = sorted dir names under `<tree>/skills/` that contain a `SKILL.md`. (3) `extracted_skills(profile_path)` = sorted unique `<name>` from `08_skills/<name>/SKILL.md` arguments following each `skill_sections.sh` token (the path is on the next continuation line in `profiles/augustus_content_task.md:92-93`; parse the file as one string with `\\\n` joined, then regex). (4) the join loop, counted, emitting the report line and SUMMARY keys in §3 above, placed after the runner join block (`:265-304`) so the report order stays stable.
- `tests/test_workflow_coverage.sh` — parse the new report line (`skills_checked`, `skills_of`, `skills_he`), a `skills_join_checked_every_entry` guard mirroring `runner_join_checked_every_entry` (`:106-111`) plus the heading-extraction count against `live_he`, then `check skills-declared`, `check skills-mechanism`, `check skills-join`, and `assert '...' skills_join_checked_every_entry  # (::skills-join-counted)`; the four negative fixtures of §5.
- `design/fleet-suites.toml` — append the four ids to the coverage suite's `asserts` (`:66-79`), one comment each, `# T3.2:` prefix like the T1.2 lines.
- `design/agent-model.md` — §4 schema block (`:219-303`): document `skills` (REQUIRED on every entry) and `skills_mechanism` (optional; only value `"heading-extraction"`; absent = the runner's `--plugin-dir`) directly after `suite_exempt`; note the kanban `skills = 25` is a different concept. §"Skills are two mechanisms" (`:158`): a dated paragraph with the bet numbers of §6. §8 decision 4 (`:702`): one dated line.
- `profiles/augustus_content_task.md` — prepend the `Owner: augustus — ...` line (§7). Deployed copy follows via `bin/deploy`.
- `docs/dev-plan-2026-09.md` — T3.2 row `:235-239` DONE paragraph; `:589` and `:594` (§9). The row's "1 of 13" is already right (the tree has 13; the Notion card's "14" is the pre-T3.1 count — leave Notion prose alone).
- `skills/README.md` — `:66-71` (§9).

## Files to create

- none. The join lives in the existing coverage suite (`tests/test_workflow_coverage.py` + `.sh`), which `bin/verify.sh` already runs; a new `tests/*.sh` would need its own `[[suite]]` entry and an owner for no gain.

## Test plan

- `python3 tests/test_workflow_coverage.py` alone: report shows `skills join: checked 33 of 33 entries, 2 heading-extraction, 12 with a non-empty offer`, SUMMARY carries the three keys, zero `PROBLEM\tskills-*` lines.
- `bash tests/test_workflow_coverage.sh`: the four anchors pass; the four negative fixtures each produce exactly the expected id and nothing else; `asserts-anchored` / `asserts-join-counted` stay green (ids declared and anchored both ways).
- `bash tests/test_fleet_ownership.sh`: `profile-owner-header` now covers `augustus-content` and `content-change-dispatch` (two more profile-carrying entries) and passes.
- `bash tests/test_content_skill_extract.sh`: unchanged and green after the line-1 prepend.
- `bash tests/test_pointer_skills.sh`: unchanged and green — it already proves each scheduled runner offers its **owner's** tree behind a guard (`runner-offers-owner-tree`, `runner-skills-guard`); the new join must not re-assert that, only read the tree the runner names.
- `bash tests/test_workflow_registry_frozen.sh`, `bash tests/test_manifest_surfaces.sh`: green — neither compares entry keys (checked 2026-09-11).
- `bin/check_deploy_drift.sh` green after `bin/deploy`; then the full `bash bin/verify.sh`.
- Hand check, once: `git diff --stat design/agents/` touches exactly 5 files; `grep -c '^skills *= ' design/agents/*.toml` sums to 33 (+5 if you count the kanban numerics — exclude them with `grep -c '^skills *= \['`).

## Out of scope / do not touch

- **No new runner, no `--plugin-dir` for augustus or trajan.** Their empty/heading-extraction declarations are the recorded state (`skills/README.md`); closing the gap by wiring a plugin dir into codex-acp or a platform timer is a different task.
- **T3.3 (invocation telemetry)** — this task declares and joins the *offer*; it measures nothing about whether a skill was read.
- `bin/` scripts and `systemd/` units — unchanged. `bin/skill_sections.sh` and its test are the mechanism, not the subject.
- `tests/test_pointer_skills.sh` — do not duplicate its owner-tree assertions in the coverage suite.
- The T1.2 runner join's behaviour (`model-alias`, `runner-tools`, `runner-mcp`, `runner-join-counted`) — the `assigns` refactor must leave its outputs byte-identical; diff the report before/after.
- `[surfaces.kanban] skills = 25` on all five manifests — retired-surface numeric, a different concept under the same key; the join reads `[[workflows]]` only.
- Vault (`08_skills/`), `~/.config/*`, Notion card prose. The card's Status may be set to Done after the push (`notion_update_page` over `/run/user/1000/buzz-notion.sock`), but that is not part of the gate.
- `.claude/briefs/t4-4-platform-contracts.md` and the `feat/t4-4-platform-contracts` branch — another job's work in the shared checkout on 2026-09-11; branch from `main`, not from it.

## Notes / preconditions

- Measured 2026-09-11 in `~/dev/agent-workforce` at `main` = `2d7d7f0`: 33 entries; `--plugin-dir` present in exactly nine runners (`bin/run_{m1_signal_scan,bd_followup_drafts,raw_ingest,standing_research,knowledge_digest,bd_stall_radar}_cc.sh` → `skills/claudius`; `bin/run_{overnight_morning_report,daily_rhythm,weekly_pre_assembly}_cc.sh` → `skills/marcus`); `praetorium-daily-plan` and `praetorium-eod-summary` both name `bin/run_daily_rhythm_cc.sh` as runner, hence 10 plugin-dir entries from nine files. Trajan's platform entries resolve to no runner file except `agent-drift-check` and `agent-buzz-acp-update`, whose scripts carry no `--plugin-dir` — all 16 correctly `[]`.
- Pointer tree (T3.1): augustus `blog-engine linkedin-content-engine linkedin-review`; claudius `investment-research meeting-prep prospect-research`; marcus `agent-inbox-sync post-call-capture weekly-review`; trajan `spec-to-code-enforcement systematic-debugging test-driven-development verification-before-completion`; aurelian none (no `skills/aurelian/`).
- The only `skill_sections.sh` caller in `profiles/` is `augustus_content_task.md:92-101`, one invocation, target `~/vault/08_skills/linkedin-content-engine/SKILL.md`, nine sections. `augustus_polish_task.md` names `linkedin-content-engine/references/*.md` by path with no extractor call — it is not a live workflow's profile and is not declared anywhere; leave it.
- `runner_file()` already handles `bin/agent_propose.sh -> bin/run_content_via_buzz.sh` (splits on `->`, returns the first existing file = `agent_propose.sh`, which has no `--plugin-dir`). The heading-extraction branch therefore keys on `skills_mechanism`, never on the runner — that is why the field exists.
- `tests/test_workflow_coverage.sh` scopes `pipefail` off inside `assert()` and uses the `yes | grep -q y` canary; keep new fixture pipelines inside `assert` or a function that does the same.
- Deployed tree `~/agent-workforce/` == source is asserted by `bin/check_deploy_drift.sh` over `profiles docs config CLAUDE.md AGENTS.md README.md systemd skills` (`:94`); `design/` and `tests/` are not deployed, so the manifest and suite edits alone leave drift green — the profile, dev-plan and README edits are what require `bin/deploy`.
- The shared checkout was on `feat/t4-4-platform-contracts` with a clean tree when this brief was written (T4.4 job in flight, commit `96c9019`); `main` is `2d7d7f0`. The auto-sync timer refuses to run off `main`, so nothing sweeps a feature branch. Definition of done per `docs/dev-plan-2026-09.md`: brief before code (this file), verify green, `bin/deploy` run, committed and pushed by hand.
- The Notion card says "1 of 14"; the repo tree and the dev-plan row say 13 (`docs/dev-plan-2026-09.md:32` records the reconciliation). 13 is the measured figure; use it everywhere in the repo.
