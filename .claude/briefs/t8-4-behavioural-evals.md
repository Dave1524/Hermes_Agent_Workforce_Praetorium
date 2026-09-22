# Brief: T8.4 — Behavioural evals on agent-config changes

Card: `scratchpad/notion/behavioural-evals.md` (Size L, Phase 1). Source: `~/OUTBOX/sdlc-playbook-gap-2026-09-15.md:22,43`.

## Decision — the eval runs on the box, not in CI

- CI holds no credential by design (`.github/workflows/verify.yml:5-6` "no secrets"; zero `secrets.` refs). The box is
  logged in (`claude auth status` → `authMethod: claude.ai`, `~/.claude/.credentials.json` present, no `ANTHROPIC_API_KEY`),
  and nine `claude -p` runners already spend that login under timers — the precedent.
- `claude plugin eval` exists here (claude 2.1.278; `--help` read 2026-09-22): target = a plugin path, cases at
  `<plugin>/evals/<case>/case.yaml`, headless via `--trust-plugin --no-publish --json`, exit 0/1/2. It runs each case as a
  full `claude` child on the caller's credential. So: CI carries the **deterministic half** (case files well-formed, baseline
  pinned + MEASURED-dated + joined to the case set); the box carries the **live half** twice — in the verify gate when a
  branch touches the watched paths, and weekly under a timer for drift with no diff (model/harness rollouts, `~/CLAUDE.md`).
- Verdict is regression-vs-baseline, not absolute (`bin/fleet_eval.sh:13-20` rationale, `bin/fleet_eval_probes.json`
  `baseline:` field). Pass `--threshold 0` to the tool; the comparator decides.

## The first eval — incident: pointer skills offered, never invoked (T3.3)

MEASURED 2026-09-22 from `~/agent-workforce/logs/cost.log` (48 records since 2026-09-15): `skills=none` ×41,
`skills=unknown` ×7, invoked ×0; `skills_offered=` lists three per owner every run. `skills/README.md:9-11` names the
credible cause: until `400e7ef` (2026-09-18) every pointer paraphrased its description and dropped the vault's
"Use when …" triggers — `meeting-prep` read `Prepare for a meeting from what the vault already knows.` (`2e359f5`), now
`… Use when Dave says 'prep for meeting with [company/person]' …` (`skills/claudius/skills/meeting-prep/SKILL.md:3`).
Case `claudius/meeting-prep-fires`: prompt = that trigger phrase with a fictitious company; grader `tool_used: Skill`,
`input_match: '"skill"\s*:\s*"(?:[\w-]+:)?meeting-prep"'`. The broken-skill fixture is the `2e359f5` description verbatim.

## Acceptance criteria

1. **Runner** `bin/agent_config_eval.sh [--owner <o>]… [--runs N] [--changed-since <ref>] [--record] [--self-check]
   [--deliver] [--quiet]`, `set -uo pipefail`, shape of `bin/fleet_eval.sh`. Copies each `skills/<owner>` (source tree when
   run from the checkout, `~/agent-workforce/skills` under the timer) to `mktemp -d` and evaluates the **copy** — the tool
   writes `<plugin>/evals/results/` and `auto-sync` would commit it within 15 min. Invokes
   `claude plugin eval <copy> --trust-plugin --no-publish --ablation none --threshold 0 --runs N --model <pinned>
   --json <copy>.json`; model pinned to the full name (`claude-sonnet-5`, the `run_*_cc.sh` convention — an alias rolls).
   `--changed-since <ref>`: exit 0 with one line `no watched path changed` unless `git diff --name-only <ref>...HEAD`
   touches `skills/`, `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/` (never `.claude/briefs/`).
2. **Comparator** `bin/agent_config_eval_compare.py <result.json>… --baseline skills/evals-baseline.json [--record]`,
   python3 stdlib, prints `check|status|value|detail` rows (`fleet_eval_grounding.py` shape). Per case:
   `score < baseline.score - tolerance` → REGRESSION (red); `>` → IMPROVED (reported, baseline untouched); baselined but
   absent → MISSING (red); present but unbaselined → UNBASELINED (red: measure before it lands). `tolerance` defaults to
   `1/runs` so one flaky run of three is amber, two are red. Exit 1 on any red. `--record` is the only writer of the baseline.
3. **Baseline** `skills/evals-baseline.json`: `measured` (ISO date), `claude` version, `model`, `runs`, `tolerance`,
   `cases.{owner/case}.score`. Written by `--record`, re-recorded only by a deliberate commit (`fleet_eval.sh:19-20`).
4. **Case** `skills/claudius/evals/meeting-prep-fires/case.yaml` (`schema_version "1.1"`, `runs: 3`, `max_turns: 4`,
   `timeout_seconds: 180`, `allowed_tools: [Skill]`, one `tool_used` grader). Sits beside `skills/`, not inside it —
   `tests/test_pointer_skills.sh:85-93 tree_pairs` walks only `skills/<owner>/skills/*/`, so the twelve pointer groups are
   unaffected; `owner_dirs` (`:76-82`) treats every dir under `skills/` as an owner, so **nothing eval-shaped goes at
   `skills/evals/`**.
5. **Gate** `tests/test_agent_config_eval.sh`: fixture groups run everywhere; the live group runs on the box only when the
   branch diff touches a watched path (or `AGENT_CONFIG_EVAL_LIVE=1`; `=0` opts out), else one `SKIP:` line. Off the box
   it prints `SKIP: test_agent_config_eval.sh — the claude.ai login the live eval spends (absent: ~/.claude/.credentials.json)`
   via `box_only_with`, pinned in `tests/ci-expected-skips.txt`. The change-gated skip line on the box is never diffed.
6. **Red on a broken skill** (`--self-check`): copy `skills/claudius`, overwrite meeting-prep's description with the
   fixture, run against the real baseline, require exit 1 naming `meeting-prep-fires`; then the clean run, require exit 0.
   Proven in PR1's body with both `check|status` tables; standing under the timer; opt-in in the gate (cost).
7. **Timer** (PR2) `systemd/agent-config-eval.{service,timer}`: `Sat 08:07`, `RandomizedDelaySec=90s`,
   `Persistent=true`, `ExecStart=… --self-check --deliver`, no `OnFailure=` (`design/contracts/fleet-eval.md:9-13`
   reasoning), **shipped disabled** — no task enables a timer. Owner trajan.

## Files to modify

- `tests/ci-expected-skips.txt` — one line + dated paragraph (appended, never interleaved: file header rule).
- `design/fleet-suites.toml` — `[[suite]] path="tests/test_agent_config_eval.sh" owner="fleet"` with anchors (PR1); if
  `tests/test_workflow_coverage.py` rejects a suite claimed by both a manifest row and this file, drop it here in PR2.
- `.gitignore` — `skills/*/evals/results/` (belt; the runner never writes the checkout).
- `skills/README.md` — § "Behavioural evals": add a case, record, read the table (~15 lines).
- PR2: `design/agents/trajan.toml` (`[[workflows]] unit="agent-config-eval" … status="standing" alerted=false`, notes as
  `:79-95`), `config/fleet-units.tsv` (`agent-config-eval	system	standing	trajan	timer`, mirrors `:71`; receipts then come
  from `bin/receipt_sweep.py:7` generically), `docs/runbook.md` § Job wiring + a short § Agent-config evals.
  `design/workflow-registry.md` is frozen — do not edit (`tests/test_workflow_registry_frozen.sh:1-16`).

## Files to create

- `bin/agent_config_eval.sh`, `bin/agent_config_eval_compare.py`, `skills/evals-baseline.json`,
  `skills/claudius/evals/meeting-prep-fires/case.yaml`.
- `tests/test_agent_config_eval.sh`; fixtures under `tests/fixtures/agent-config-eval/`: `meeting-prep.paraphrased.md`
  (the `2e359f5` frontmatter), `result-{equal,drop,improve,missing,unbaselined}.json` (hand-cut from one real `--json`).
- PR2: `systemd/agent-config-eval.service`, `systemd/agent-config-eval.timer`, `design/contracts/agent-config-eval.md`
  (light T4.4 contract, `fleet-eval.md` layout).

## Test plan

`tests/test_agent_config_eval.sh` — anchors `# (::<id>)` on each group's opening line, all declared in fleet-suites.toml:
- `(::eval-case-wellformed)` every `skills/*/evals/*/case.yaml` has `name` == its directory, a `prompt`, ≥1 grader with
  `type`; grep/awk only — **no PyYAML on the box** (`python3 -c "import yaml"` → ModuleNotFoundError, 2026-09-22).
- `(::eval-case-names-skill)` each grader `input_match` names a pointer that exists under that owner's `skills/`.
- `(::baseline-measured-dated)` baseline parses, `measured` ≤ today, `model`+`claude` non-empty, and its case set equals the
  tree's — both directions. This is the CI-side half of "pinned": a case without a recorded score is red on a runner.
- `(::compare-regression-red)` the five fixture results → exit 1/0/0/1/1, red rows name the case; `(::compare-record-writes)`
  `--record` on a scratch baseline stamps today and the model.
- `(::watched-paths-trigger)` on a scratch repo: a commit touching `skills/x` → runner would run; `.claude/briefs/x` → skips.
- `(::live-eval-clean)` box + change-gated: `bin/agent_config_eval.sh --changed-since origin/main` exits 0.
- `(::broken-skill-turns-red)` `AGENT_CONFIG_EVAL_LIVE=1` only: `--self-check` exits 1 then 0.
- `yes | grep -q y` canary; `assert()` scopes pipefail off (CLAUDE.md § Verification).
Also: `bash tests/test_pointer_skills.sh` unchanged green with `evals/` present; PR2 `tests/test_fleet_ownership.sh`,
`tests/test_receipt_coverage.sh`, `tests/test_workflow_coverage.py` green; `bin/check_deploy_drift.sh` after `bin/deploy`.

## Out of scope

- Editing any vault `08_skills/*/SKILL.md` or pointer text; enabling the timer; `bin/verify.sh`, `bin/check_deploy_drift.sh`,
  `.claude/hooks/ship_rails.py` (protected); `bin/fleet_eval.sh` (its contract says "no LLM", `design/contracts/fleet-eval.md:21`).
- Evals over Buzz agents' `.prompt` charters or `~/CLAUDE.md` — not plugin-shaped; a later card.
- Fixing the T3.3 zero itself (job prompts not matching triggers is a finding this eval will make legible, not fix).

## Notes / preconditions

- Verify first, in PR1 step 1, before any file: with `--ablation none` a `tool_used: Skill` grader **scores** (under
  `with-without` it is indicator-only, `--help` "Ablation"). If it does not, fall back to a `regex` grader on the final output
  for the pointer's `Canonical source:` line. Also read one real `--json` to pin the score path the comparator walks.
- The eval's scaffold cwd is the tool's; if it sits under `/home/dave`, `~/CLAUDE.md` (46 KB) and the shared memory pool
  load into every run. Measure per-run wall time and turns on the first clean run and write both into the baseline `_comment`.
- `--max-cost-usd` under the claude.ai login is unverified; bound runs by `max_turns`/`timeout_seconds` instead.
- Deploy ships `evals/` into `~/agent-workforce/skills` (`bin/deploy:20`); the plugin loader ignores it, and
  `runner-skills-guard` only reads `plugin.json`. Loop is edit → deploy → verify → commit; commit before the 15-min sweep.
- Run the ~10-min gate detached; `sudo` is passwordless for the PR2 unit install.

## Order of work

**PR1 — smallest thing that turns red on a broken skill.** Runner (no `--self-check`/`--deliver`), comparator, the one
case, `--record` the baseline (MEASURED-dated), suite groups 0-6 + `(::broken-skill-turns-red)` run by hand and pasted into
the PR body, skips line, fleet-suites entry, `.gitignore`, README §. Green alone: on CI everything but the live group; on
the box the live group runs because the branch touches `skills/`.
**PR2 — standing.** `--self-check` + `--deliver` (ops route, only on red, `fleet-eval.service` precedent), unit pair
shipped disabled, manifest row, fleet-units.tsv row, contract, runbook. Green alone: units drift-red until `sudo cp` +
`daemon-reload` (not `enable`).
**PR3 — coverage.** One case per pointer (12 today: `ls skills/*/skills/`), `(::every-pointer-has-eval)` join both ways,
`-j 4`, baseline re-recorded once with the twelve. A `max: 0` negative case (an off-trigger prompt must not fire a skill)
per owner is the cheapest second incident class.

## Risks

- Score quantisation at 3 runs (0/.33/.67/1) makes one flaky run a 0.33 drop; `tolerance=1/runs` absorbs one, not two.
  If the weekly run is noisy, raise `runs`, never the tolerance.
- Shared rate limit: each case run is a full `claude` child on the same login as five Buzz agents and nine runners;
  `Sat 08:07` is clear of every timer slot (`systemd/fleet-eval.timer` header list) and the working week.
- The card says "a CI job"; this brief satisfies the intent on the only surface with a credential and keeps the
  deterministic join in CI. Say so in the card's Brief note rather than letting the acceptance line read as unmet.
- Model rollout moves scores with no diff — that is the timer's job, and a red there is re-recorded by hand, not auto-bumped.
