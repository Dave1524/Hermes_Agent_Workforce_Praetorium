# Brief: S1 capability isolation — per-agent skills and tools on the Buzz fleet
**Date:** 2026-09-18   **Verify:** `bash bin/verify.sh` from the repo root, then
`~/.config/buzz-team/verify-fleet.sh` and `~/.config/buzz-team/check-loaded.sh` after deploy.

Source of scope: Dave, 2026-09-18 — "the main reason why we started this refactor was to give
each agent their own distinct tools and skills". `docs/dev-plan-2026-09.md` is closed at the
questionnaire; this is its own card, not an appended task. Plan (approved):
`~/.claude/plans/drifting-tinkering-hejlsberg.md`. Decisions taken there: **full isolation** on
the Claude side (agents load the bridge, `~/CLAUDE.md`, their rendered settings and their owner
skill tree — nothing of Dave's user scope); **aurelian enforced as declared** (deny
`Edit`/`Write`/`NotebookEdit` and the seven `notion_*`; `Bash` stays).

**Measured state before (2026-09-18, live units):** no `buzz-agent@*` session is offered a
pointer skill; the four Claude sessions run `--setting-sources user,project,local` without
`--strict-mcp-config`, so they load Dave's user MCP servers (`brave-search` with his key,
`graft`, `google-docs`, `qmd`), `HA`, the `shared@jbuitenhuis` plugin and every claude.ai
connector the deny list did not name — Eden and Claude Docs were open until `ad41fd1`.

## Acceptance criteria

1. **Manifest is the source.** Every `design/agents/<name>.toml` `[surfaces.interactive]` carries
   `tools` (family string), `tools_deny`, `bridge_tools`, `mcp = ["buzz-team-mcp"]`; every
   `buzz-agent@<name>` entry carries `skills` = the owner's pointer names and
   `skills_mechanism = "acp-wrapper"` (Claude) or `"codex-home"` (augustus); aurelian `[]`.
2. **Rendered, never hand-written.** `bin/fleet_capabilities.py render` emits
   `buzz-team/agent-settings-<name>.json` ×4 and `buzz-team/buzz-team-mcp-<name>` ×5;
   `check` fails when the committed files differ. All nine are `[[adopted]]` in
   `buzz-team/MANIFEST.toml`.
3. **Skills reach S1.** Claude agents: the wrapper appends `--plugin-dir
   $HOME/agent-workforce/skills/$BUZZ_AGENT_NAME` behind the runners' readability guard; the
   unit sets `BUZZ_AGENT_NAME=%i`. Augustus: `$CODEX_HOME/skills/praetorium` resolves to the
   deployed `skills/augustus/skills`. Aurelian: an empty owner plugin, so the guard is uniform.
4. **Tools are isolated.** Wrapper flags after `"$@"`: `--strict-mcp-config`,
   `--setting-sources=` (none — the agents' cwd is `/home/dave`, so the *project* settings
   file is `~/.claude/settings.json` itself; measured 2026-09-18, `project,local` still
   loaded it), `--settings <per-agent>`, `--plugin-dir`. `~/CLAUDE.md` and the auto-memory
   pool are not settings and still load (measured). The bridge shim
   per agent (`--mcp-command %h/.config/buzz-team/buzz-team-mcp-%i`) execs
   `buzz-team-mcp.py --agent <name> --tools <bridge_tools>`; the bridge filters `tools/list`
   and refuses `tools/call` outside the set. Per-agent settings = base ∪ `tools_deny` ∪ denies
   for bridge families not in `bridge_tools` ∪ the connector deny.
5. **Pointer descriptions are the vault's.** `bin/pointer_skills_sync.py render` mirrors the
   canonical `description` verbatim into each of the 13 pointers and the body names the
   canonical directory; `check` is box-gated in `tests/test_pointer_skills.sh`
   (`pointer-description-synced`).
6. **Joined by tests.** `tests/test_workflow_coverage.py` derives the S1 offer from the mechanism
   (`acp-wrapper` → pointer names of `skills/<owner>` and the wrapper flag; `codex-home` →
   the same tree and the link name); new `tests/test_fleet_capabilities.sh` (declared in
   `design/fleet-suites.toml`) asserts render == committed, per-agent superset of the base deny,
   wrapper flag order, shims, bridge filter == manifest, aurelian's declared deny, and the
   connector deny complete against a fixture.
7. **Proven live.** verify-fleet gates 14/15: each Claude `claude` child's cmdline carries the
   four flags and its own files; no MCP child in the unit cgroup but the bridge; augustus's
   symlink resolves; each shim's `tools/list` equals its manifest from the host and, for
   augustus, inside his namespace.
8. **Use is measured.** S1 receipts carry `skills_offered` and `skills` (invoked/read) via
   `bin/skill_telemetry.collect`; `bin/scorecard.sh` folds them into the T3.3 table.
9. **Cost is recorded.** `context-cost.py` per agent before and after, both figures in the
   landing commit.

## Files to modify
`buzz-team/{claude-agent-wrapper.sh,buzz-team-mcp.py,agent-settings.json,MANIFEST.toml,verify-fleet.sh}`,
`systemd/user/buzz-agent@.service`, `design/agents/*.toml`, `design/fleet-suites.toml`,
`design/agent-model.md`, `skills/README.md`, `skills/*/skills/*/SKILL.md` ×13,
`tests/{test_workflow_coverage.py,test_buzz_team_mcp.py,test_fleet_guards.sh,test_pointer_skills.sh}`,
`bin/{interaction_receipt.py,scorecard.sh}`, `docs/runbook.md`, `~/CLAUDE.md`.

## Files to create
`bin/fleet_capabilities.py`, `bin/pointer_skills_sync.py`, `buzz-team/agent-settings-<name>.json` ×4,
`buzz-team/buzz-team-mcp-<name>` ×5, `skills/aurelian/.claude-plugin/plugin.json`,
`tests/test_fleet_capabilities.sh`, `tests/fixtures/claude-ai-connectors.txt`.

## Out of scope
`~/.claude.json` readable by agents (separate decision); builtin allowlists beyond aurelian;
new pointer skills; codex `skills.config` disable rules; `BUZZ_AUTH_TAG` in the two drop-ins.

## Land-time steps
`bin/deploy` → `bin/deploy_buzz_team.sh` → install the unit + `daemon-reload` → codex symlink →
restart the five units when idle → `check-loaded.sh` → both fleet gates → `bin/verify.sh` →
commit and push by hand. The drift check is red on the branch until then, by construction.

## Landed 2026-09-18 (box side; PR pending Dave's merge)

Land-time steps ran in order: `bin/deploy` (4 paths), unit installed + `daemon-reload`,
`~/.config/codex-agents/augustus/skills/praetorium -> ~/agent-workforce/skills/augustus/skills`,
`bin/deploy_buzz_team.sh` (13 files), the five units restarted one at a time at ~21:20 CEST
with no live turn (marcus's last turn ended 21:08:04, `end_turn` + stop hook recorded;
`NRestarts=0` on all five afterwards), `check-loaded.sh` all OK, `verify-fleet.sh` PASS with
gates 14 and 15 (14/session skipped out loud on all four — no `claude` child between turns;
15/offer read `qmd,notion,brave` on marcus/claudius/trajan/augustus host **and** augustus
namespace, `qmd,brave` on aurelian; augustus's namespace reads
`skills/praetorium/blog-engine/SKILL.md` through the link), `bin/verify.sh` rc=0, drift clean.

**Cost (criterion 9).** Headless `claude -p ok` with the adapter's flags, cwd `~`, model
sonnet, before vs after the wrapper's four flags: 15 MCP servers → 1 (the bridge);
78 tools → 45 (aurelian 33); 38 skills, none a pointer → the owner's pointers + Claude
Code's bundled set; prompt context 63,912 → 34,593 tokens (cache_creation + cache_read),
$0.1645 → less than half. `context-cost.py 14` before the restart: static layers marcus
93,656 B / claudius 48,732 B per request (`[Base]` 13,684; the rest is charter, team and
memory, untouched by this change). The after figure from `context-cost.py` needs a real
turn on the new wrapper and is recorded on the first one, together with the first receipt's
`skills.offered` per agent (criterion 8's live half).

One finding the plan had wrong: the `claude` child does **not** exist only mid-turn — marcus's
lingered 11 minutes after `end_turn`. Gate 14 is right to read it opportunistically and skip
out loud; "no child" still does not mean "no session".

**First turns, 2026-09-18 21:34–21:49 CEST (marcus, DM).** Receipt 1: `skills.offered` ==
manifest. Receipt 2 (weekly-review): `invoked: ["weekly-review"]` — and `read: []` for a turn
that cat-ed the canonical file, which is PR #55 (a shell command naming a SKILL.md is a read).
Gate 14 read the live session: four flags on the `claude` child, the bridge its only MCP child,
qmd the bridge's only child.

**After figure (criterion 9), measured from transcript usage, not `context-cost.py`** — that
script keys on `[Base]`/`[System]` text blocks in the first user record, and the current
buzz-acp puts `<context>` / `<conversation-context>` / `<buzz-event>` there instead, with the
static layers in the system prompt the transcript never records; it reports "No fleet turns"
for every session since the harness upgrade and needs rewriting before it measures anything
again. Same agent, same DM channel, same shape (first request, owner DM with full scrollback):
2026-09-16 17:25 → 156,600 tokens, of which ~42.5k the 89-message scrollback, **114,088 the
rest**; 2026-09-18 21:34 → 129,829, ~42.8k scrollback, **87,026 the rest**. −27,062 per
request (−23.7%), in line with the headless probe's −29k, resent on every one of the turn's
116 requests. The scrollback is now the largest single layer of a DM turn and unchanged by
this work — `BUZZ_ACP_CONTEXT_MESSAGE_LIMIT`'s question, not S1's.
