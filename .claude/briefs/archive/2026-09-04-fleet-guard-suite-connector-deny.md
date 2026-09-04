# Brief: Deny the outward connectors for agent sessions, and assert every enforced must-not rule
**Date:** 2026-09-01   **Verify:** `bash bin/verify.sh` from the repo root (syntax + shellcheck -S error over `bin/`, then every `tests/*.sh`)

> ## STATE — 2026-09-04: DONE. Archived.
>
> Phase-B brief 1 (D1 + D9). Its work landed 2026-09-01 and
> `design/phaseb-brief-queue.toml` records both halves from the outside: line 38 —
> "The `fleet` owner value landed with brief 1: `design/fleet-suites.toml` declares
> `owner = "fleet"`" — and line 20, that `buzz-agent@.service` "was edited on 2026-09-01
> by brief 1 to add `CLAUDE_CODE_EXECUTABLE`". Later briefs then built on it: D8's drift
> check adopted that unit tree, and W6 closed the suite-ownership half it opened.
>
> Archived unbannered until now, which is the only reason it sat loose in
> `.claude/briefs/` for three days after it was finished.

This is Phase-B brief 1, and it is D1 and D9 together. They merged because D9's measurement
found that seven of the eight outward `must_not` rules are `enforced = false` *precisely
because* D1's mechanism is not installed. Installing a mechanism and writing the test that
fails when it is removed is one unit of work; splitting it ships a mechanism nobody checks.

Read `design/open-decisions.md` D1 (line 37) and D9 (line 766) before starting. This brief does
not restate their measurements — it states what to build.

## Acceptance criteria

1. **Agent sessions cannot reach Gmail, Microsoft 365, Google Drive or Figma.** The four
   `mcp__claude_ai_*` families are denied for every `claude-agent-acp` agent session.
2. **Dave's own interactive sessions on this box keep them.** `~/.claude/settings.json` is not
   modified by this brief. The split is real, not a global tightening.
3. **The split is proven by what the running process loaded, not by what a file says.** After
   wiring, a live agent's `claude` process carries `--settings` in its argv, and a transcript
   written after the restart contains **zero** tool definitions for the four denied families
   while still containing `mcp__qmd-mcp__*` as a positive control.
4. **The strict file is a superset of the base file**, and a deny added to the base and not the
   strict file is a red gate.
5. **The vault main-push guard is installed in every vault clone on this box that has a push
   remote** — which today means installing it in `~/dev/obsidian-ai-os-boxsafe`, where it is
   absent. The gate must be **green** when this brief is done, so the red that D9 predicted is
   fixed here rather than shipped.
6. **`tests/test_fleet_guards.sh` exists** and asserts all six currently-enforced `must_not`
   rules plus the two structural invariants (superset, declaration well-formedness).
7. **Every `enforced = true` rule in every manifest names a test that exists and contains the
   assertion it names.** A flag that claims enforcement with nothing checking it is a red gate.
   This is D9's redefinition made machine-checkable: *`enforced = true` iff a machine-checkable
   artifact exists whose removal or absence a test can detect.*
8. **`design/fleet-suites.toml` exists and declares `owner = "fleet"`,** and
   `design/eval-spec.md` documents that value as part of D6's declared join. Without this,
   brief 3's coverage checker classifies this suite as an orphan and recommends deleting the
   security tests as its first act.
9. `bash bin/verify.sh` exits 0.

## Files to create

- **`~/.config/buzz-team/agent-settings.json`** — the strict settings file. A **superset**:
  every entry currently in `~/.claude/settings.json`'s `permissions.deny` (10 secret-path
  entries + `mcp__claude_ai_Notion`) **plus** `mcp__claude_ai_Gmail`,
  `mcp__claude_ai_Microsoft_365`, `mcp__claude_ai_Google_Drive`, `mcp__claude_ai_Figma`.
  Written as a superset deliberately, so it is correct whether `--settings` merges or replaces.
  Match the existing entry form exactly — the live Notion deny is the bare server name
  `mcp__claude_ai_Notion`, not `mcp__claude_ai_Notion__*`.
  Carry `permissions.deny` only. Do **not** copy `model`, `effortLevel`, `enabledPlugins`,
  `autoCompactWindow` or any other key from the base file: this file exists to tighten one
  thing, and every key it duplicates is a second drift surface.

- **`~/.config/buzz-team/claude-agent-wrapper.sh`** — `exec claude --settings <strict> "$@"`,
  with the PATH preamble the sibling wrappers use (a unit's PATH from `/etc/environment`
  excludes both linuxbrew and `~/.local/bin`; see `/usr/local/bin/claude-agent-acp`). Mode 755.

- **`tests/test_fleet_guards.sh`** — the guard suite. See Test plan.

- **`design/fleet-suites.toml`** — the D6 schema amendment. One array of tables:
  ```toml
  [[suite]]
  path    = "tests/test_fleet_guards.sh"
  owner   = "fleet"
  asserts = "the enforced must_not rules across design/agents/*.toml"
  why_no_workflow = "a fleet-wide invariant is owned by no single workflow; D6's reachability rule would otherwise classify it as an orphan"
  ```
  Keep the schema this small. It exists to give the checker a second valid owner value, not to
  become a second registry.

## Files to modify

- **`~/.config/systemd/user/buzz-agent@.service`** *(out of repo — see Notes)* — add
  `Environment="CLAUDE_CODE_EXECUTABLE=%h/.config/buzz-team/claude-agent-wrapper.sh"` alongside
  the existing `BUZZ_ACP_*` Environment lines at 14-30. It belongs in `Environment=`, not on
  `ExecStart`, for the reason the unit's own comments already give: a value on `ExecStart`
  cannot be overridden from a drop-in.

- **`design/agents/marcus.toml`, `claudius.toml`** — flip `"send email or any outward message"`
  to `enforced = true`, `why` naming the strict settings file as the mechanism, and add the
  `test` field (below).

- **`design/agents/augustus.toml`** — flip the same rule to `enforced = true` but with a
  **different `why`**: augustus runs `codex-acp` inside bwrap, and the claude.ai OAuth
  connectors are a Claude Code surface he has never had. The strict settings file does not
  reach him and must not be credited for him. Crediting the wrong mechanism is the exact defect
  D3 found in `agent-model.md` §2/§6.1; do not reproduce it here.

- **`design/agents/trajan.toml`** — the `"push the vault main branch"` rule keeps
  `enforced = true`, but its `why` currently reads *"box holds no canonical vault credential;
  boxsafe pre-push hook"* and the second clause was false when written. Correct it to name the
  guard as installed in **both** clones, and do not let it overclaim: the guard's own header
  says it is *"friction and a record, not a boundary"* — the box's deploy key is a ruleset
  bypass actor server-side, so an unguarded push is accepted and merely logged.

- **all five manifests** — add a `test` field to every `enforced = true` rule, of the form
  `test = "tests/test_fleet_guards.sh::<assertion-id>"`. The suite asserts, in reverse, that
  each named file exists and contains each named id. This is what makes the flag non-forgeable.

- **`design/eval-spec.md`** — document `owner = "fleet"` and `design/fleet-suites.toml` as part
  of D6's declared join, and record the redefinition of `enforced` in criterion 7. Brief 3's
  implementer reads this file, not this brief.

- **`design/agent-model.md` §6.1** — it records the live connectors as an open gap. Record the
  closure with the mechanism and the date. Do not restate D1's measurement; link it.

## Test plan

One file, `tests/test_fleet_guards.sh`, following the conventions in
`tests/test_buzz_unit_wiring.sh` verbatim: `set -uo pipefail`, the `assert()` helper that scopes
`pipefail` **off** inside the condition, and the `yes | grep -q y` canary as its first assertion.
That canary is not decoration — a condition evaluated under `pipefail` fails a true assertion and
silently passes a negated one, which is how this gate certified nothing for a while in August.

Seven groups:

1. **outward connectors denied** *(`::connector-deny`)* — the four `mcp__claude_ai_*` families
   appear in the strict file's `permissions.deny`; the strict file is valid JSON; the wrapper
   exists, is executable, and its `exec` line names the strict file; the unit carries the
   `CLAUDE_CODE_EXECUTABLE` line and it resolves to the wrapper that exists on disk.
2. **strict is a superset of base** *(`::deny-superset`)* — every entry in
   `~/.claude/settings.json`'s `permissions.deny` is present in the strict file. Fails red when
   a deny is added to the base file only.
3. **vault push guard** *(`::vault-push-guard`)* — for every vault clone on this box with a push
   remote, `.git/hooks/pre-push` exists, is executable, and contains the marker
   `vault-main-push-guard`.
   **Discover the clones; do not hardcode two paths.** A hand-maintained whitelist is the exact
   defect class this repo keeps rediscovering — a check that asks a list whether it is fine
   cannot fail. Rule: a directory under `~/dev` that is a git clone, contains `00_system/`, and
   has a push remote. Assert additionally that the resolved target of `~/vault` is among the
   clones found, so a vault clone living outside `~/dev` cannot be missed.
4. **aurelian unaddressable** *(`::aurelian-unaddressable`)* — `aurelian` does not appear in
   `bin/buzz_agents.env`. Absence from the slug table is what makes him unreachable by any
   scheduled delivery.
5. **propose write boundary** *(`::propose-write-boundary`)* — `bin/agent_propose.sh` still
   confines proposal-mode writes to `_inbox/agents/**` and discards everything on a violation
   (`bin/agent_propose.sh:378-382`). One assertion covers marcus and claudius, who share it.
6. **augustus cannot fetch** *(`::augustus-no-fetch`)* — `/usr/local/bin/codex-acp` mounts a
   tmpfs over `$HOME/.ssh`, so `git fetch` has no credential inside his namespace.
7. **enforced flags are backed** *(`::enforced-has-test`)* — every `enforced = true` rule in
   `design/agents/*.toml` names a `test`, that file exists, and the assertion id after `::`
   appears in it. Plus: `design/fleet-suites.toml` parses, every `path` in it exists, and this
   suite is declared there with `owner = "fleet"`.

**The constraint that governs every assertion here, and it is not negotiable: a negative test
asserts the ABSENCE OF CAPABILITY. It never attempts the forbidden action.** You cannot test
"must not send email" by sending email — the test would *be* the violation, and a "safe" test
recipient is still an outward action from a box whose entire charter is that it performs none.
Every assertion above is about the state of a mechanism: a config key, an installed hook, an
absent credential, a namespace that lacks a path. If you find yourself writing a test that
performs the act to see whether it is blocked, stop and re-read this paragraph.

**Live verification, separate from the suite** (the suite reads files; this reads the process):

- `systemctl --user daemon-reload`, then restart the four `claude-agent-acp` agents.
- Prove the running process loaded it, do not trust the file: the unit's mtime must be older
  than `systemctl --user show buzz-agent@<name> -p ExecMainStartTimestamp`, and the live
  `claude` child's argv must contain `--settings`. **Grep for the flag; never paste raw
  `ps`/`systemctl status` output for a `buzz-agent@*` unit — the agent nsec is in argv.**
- Then the schema check, which is the one that actually proves the deny took effect: in a
  transcript written *after* the restart, the four denied families contribute **0** tool
  definitions and `mcp__qmd-mcp__*` is still present. Assert the transcript glob matched a
  non-empty set before believing any zero — D1's first measurement globbed a path that did not
  exist and returned a clean `0` for every connector.

## Out of scope / do not touch

- **`~/.claude/settings.json`.** Not one line. The split exists so Dave keeps these tools.
- **`CLAUDE_CONFIG_DIR`** as the seam — rejected in D1. It relocates credentials, projects and
  the shared file-memory pool at `~/.claude/projects/-home-dave/memory/` that all four agents
  and Dave's own sessions deliberately share.
- **`--settings` via `BUZZ_ACP_AGENT_ARGS`.** It would be accepted and ignored: `index.js`
  parses only `--version`/`-v` from argv, and caller options arrive over ACP `_meta`. It would
  look configured and do nothing.
- **augustus's harness.** Codex has no claude.ai connectors and no equivalent seam. Do not
  invent one, and do not widen his bwrap namespace for any reason.
- **aurelian's `"execute anything"` rule** stays `enforced = false`. The pin is unattestable by
  construction; an INCONCLUSIVE verdict from him is correct behaviour, not a fault.
- **trajan's `"schedule recurring work on hermes cron"` rule.** It is `enforced = true` today
  but folds into D7's retirement, where it becomes moot rather than standing. Leave it; do not
  write a test for a surface brief 5 deletes.
- D8's widened drift check, D3's skill work, D7's retirement, W1–W4. Later briefs.
- Adopting `buzz-agent@.service` into this repo's `systemd/`. Tempting while you are editing it;
  it belongs to brief 2, which is where unit membership gets decided.

## Notes / preconditions

Confirmed on the box, 2026-09-01:

- `~/.claude/settings.json` `permissions.deny` holds exactly 11 entries: 5 `Read(...)` +
  5 `Edit(...)` secret paths, plus `mcp__claude_ai_Notion`. `defaultMode` is
  `bypassPermissions` — which is why `permissions.deny` is the mechanism and an
  `--allowedTools` allowlist is not; under bypass an allowlist is inert.
- `claude-agent-acp` 0.64.0 sets `settingSources: ["user","project","local"]` on the real
  session query (`dist/acp-agent.js:4156`), so `~/.claude/settings.json` **does** govern agent
  sessions today. Agents run with cwd `/home/dave`.
- `--settings` is an *additional* source — deny lists union, so a strict file can only tighten,
  never loosen. Verify this empirically anyway (the schema check above); a config claim
  validated only against a file it never loaded is a non-test.
- **`buzz-agent@.service` is not in this repo.** It exists only at
  `~/.config/systemd/user/buzz-agent@.service`. Its ExecStart is
  `~/.config/buzz-team/buzz-acp-launch.sh`, which sets `BUZZ_ACP_TEAM_INSTRUCTIONS` and execs
  `~/.local/bin/buzz-acp`; the harness is selected by `BUZZ_ACP_AGENT_COMMAND=
  /usr/local/bin/claude-agent-acp` at line 14. Environment set on the unit propagates through
  the whole chain to the `claude` child, which is what makes this seam work.
- The four agents on `claude-agent-acp` are marcus, claudius, trajan, aurelian. augustus is on
  `codex-acp` and is unaffected by the wrapper.
- **Restarting the agents drops their live sessions and re-fetches each engram.** marcus's core
  engram is at ~79% of the 65,535 B wall; the restart itself is safe, but do not do it in the
  middle of a turn you care about.
- **Vault clones, measured:** `~/dev/Obsidian_AI_Operating_System` (push remote
  `git@github-canonical:…`, on branch `agents/2026-08-17-research-fold-wms-tms`, guard
  installed 2026-08-15, 3,569 B) and `~/dev/obsidian-ai-os-boxsafe` (push remote
  `git@github-boxsafe:…`, on `main`, **no hooks at all**). `~/vault` resolves to the second.
  No other clone under `~/dev` contains `00_system/`.
- **Installing the guard in the boxsafe clone is safe, and this was checked rather than
  assumed.** The guard refuses `refs/heads/main` only — *"every other ref passes untouched"*.
  `~/agent-worktrees/inbox` is a worktree whose `--git-common-dir` is that clone's `.git`, so
  it inherits the hook; `agent_propose.sh:432` pushes `origin agents/inbox`, which the guard
  ignores. `bin/vault_sync_guard.sh` never pushes. `bin/finish_boxsafe_clone.sh:61` does a
  `push --dry-run`, but nothing invokes that script — both mentions of it in `bin/` are prose
  in error messages. Re-confirm this before installing; if a live path is found that pushes
  `main` from the box, stop and report rather than working around the guard.
- **Never reach for `--no-verify`** to get past the guard while testing. It is the same push
  with the record removed, and it is itself a `must_not` rule.
- `bin/verify.sh` already collects `tests/*.sh`, so the new suite is picked up with no gate
  change.
- **Most of what this suite asserts lives outside this repo** — `~/.claude/settings.json`, a
  `.git/hooks/` file in two other clones, a bwrap wrapper in `/usr/local/bin`, a `--user` unit.
  That is the same cross-repository pinning that silently rotted augustus's `sed` line ranges.
  It is acceptable here **only because a test is the gate the line-pins never had**: it fails
  loudly when the far side moves. So the rule for this brief is absolute — **every assertion is
  a test and none is a comment. No negative rule gets recorded as a note.**
- Commit as soon as each coherent piece is done. `agent-workforce-auto-sync.timer` fires every
  15 minutes and commits any dirty tree with `git add -A`; work left uncommitted gets swept into
  a message that describes something else.
