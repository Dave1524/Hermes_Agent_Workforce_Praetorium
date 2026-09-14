# Brief: T5.3b — Schedule changes and retirements as reviewed PRs

**Date:** 2026-09-14   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none for this task — the gate is red on the
branch for exactly the files § Land-time steps names, and green only after `bin/deploy` plus the
one sudo drop-in install there).

**Size:** M. **Depends on:** T5.3 (its `POST /api/v1/control/proposals` 501 stub, the Controls
panel with `<button data-proposal-kind="schedule|retire">`, `<pre id="control-result">`,
`bin/control_room_ui/actions.js`, `tests/control_room_fixture.py` and `systemd/control-room.service`
must exist on `main`). T5.1 landed 2026-09-11. T5.3a is **independent**: different files, and the
only shared file (`bin/control_room_api.py`) is edited at disjoint sites. T5.2 is not a dependency.

**Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF — all twelve system workflow
timers disabled since 2026-09-11 and they stay disabled. **No step in this brief enables, starts,
stops or disables a workflow timer.** Every test runs from fixtures: a local bare git remote built
at test time, a `gh` shim, a `systemd-analyze` shim and a `systemctl` shim on `PATH` (precedent:
`tests/fixtures/contract-exec/bin/systemctl`, T5.1). **No test and no code path in this brief
pushes to `origin`.** The one unit touched at land is `control-room.service` (T5.3's screen) picking
up a drop-in — a restart of the screen, not a workflow. **This brief starts no workflow run and
retires no workflow:** the evidence-time step (§ Evidence-time) is one *preview* Dave clicks and
cancels, and the first real schedule PR or retirement is Dave's moment on T5.4's evidence, not a
step here.

## Acceptance criteria

Task gate (`docs/dev-plan-2026-09.md:500-509`), the Notion card ("schedule and retire actions
produce reviewable, tested PRs and never mutate or merge workflow truth directly") and plan DoD
item 1 (`:79-85`, "schedule change and retirement produce a previewed source-repo PR") — all
satisfied:

1. **A PR, never an edit.** `Change schedule…` and `Retire…` on a workflow page produce a branch
   `control-room/<kind>-<workflow_id>-<UTC stamp>` in a **dedicated bare clone** and a GitHub pull
   request against `main` via `gh pr create`. Nothing in this brief writes `~/dev/agent-workforce`,
   `~/agent-workforce`, `/etc`, `main`, or any branch outside `control-room/*`; nothing calls
   `gh pr merge`, `git push --force`, `bin/deploy` without `--dry-run`, or a mutating `systemctl`
   verb. Asserted by grep over this brief's `bin/` sources and by the push guard's own tests.
2. **The exact diff is previewed before the PR exists.** `stage: "preview"` returns the unified
   diff, its sha256, the check results (and, for retire, the residue report) and a `preview_token`.
   `stage: "submit"` re-applies the plan on a fresh `origin/main`; if the resulting diff is not
   **byte-identical** to the previewed one the request is refused `preview_stale` with the new diff,
   and a token older than 30 min is refused the same way. The PR's diff equals the previewed bytes.
3. **A schedule PR carries** current and proposed `OnCalendar` / `RandomizedDelaySec` /
   `Persistent`, the box timezone (`Europe/Amsterdam`, DST-shifting) with the next three elapses
   local **and** UTC for both schedules, the catch-up statement (`Persistent=` × paused/active), the
   unit + manifest + contract diff, and the results of the schedule, manifest, deploy and drift
   checks (§ Checks). It names the Dave-only land steps (`sudo cp` of the timer + `daemon-reload`;
   `restart <unit>.timer` only if the timer is active — it is not, the fleet is off).
4. **A retirement PR carries** the removal across manifests (`design/agents/*.toml` entry, surface
   flag, `governed_by`), units (`systemd/` → `systemd/archive/`), runners (`bin/`), profiles
   (`profiles/` task + `.env.example`), contracts (`design/contracts/` → `design/archive/contracts/`),
   the route/producer join (`bin/buzz_producers.tsv`), the fleet list (`config/fleet-units.tsv`),
   deploy exclusions (`design/deploy-exclusions.toml`), the workflow's own suites and their
   `tests/ci-expected-skips.txt` lines, a `[[retired]]` record in `design/retired-workflows.toml`
   — **plus a residue report in the W19 table shape** (§ Residue) covering source, deployed, installed
   and deny-listed residue, and **an explicit artifact-retention decision** for receipts, Notion
   output and vault inbox artifacts, refused when any of the three is missing.
5. **Retirement fails closed.** (a) At submit: the residue scanner over the edited worktree must
   report no `executable` and no `files` residue, else `residue_in_branch` names it and no branch is
   pushed. (b) On the box: `bin/workflow_retire_residue.py --live <id>` exits 1 while any installed
   unit, staged/deployed copy or unattested deny-listed override remains, and
   `tests/test_workflow_retirements.sh` is red for every `[[retired]]` entry until
   `bin/workflow_pr.py clear <id>` — which itself refuses unless the live scan is clean — records
   `residue_cleared_on`. The deny-listed `~/.config/agent-workforce/<job>.env` is **never stat'ed**
   by any code here: it is reported as `unverifiable from an agent` with the `ls`/`rm` lines, and
   cleared only by Dave's attestation (`--env-removed`).
6. **Submit refuses on red checks.** Any check with `status: "fail"` refuses submit `checks_failed`,
   except the `pinned-tests` class (suites in the repo that name the unit and go red on the branch —
   e.g. a smoke test pinning the old `OnCalendar`, or T5.3's `tests/test_control_room_views.py`
   literals after a retirement), which submit accepts only with `acknowledge_pinned_tests: true`;
   the PR is then opened as a **draft** with a "Red on purpose until" section naming each file:line.
7. **Every request — previewed, submitted, refused, failed — writes one proposal record** under the
   state root with actor, reason, base sha, diff sha256, files, checks, residue, retention, PR
   link, refusal code and every git/gh argv with exit codes. `stage: "list"` returns them.
8. **Peer gate and vocabulary.** Missing `X-Control-Room` header, non-JSON, unknown `kind`,
   unknown `stage`, `workflow_id` outside `^[a-z0-9][a-z0-9-]{0,63}$` → 400; unknown workflow →
   404; `remote == local` or loopback-from-tailnet → 403 `peer_denied`; `kind = "service"`
   workflows (the five `buzz-agent@*`) → `not_a_timer`; `OnUnitActiveSec` timers (`qmd-refresh`) →
   `not_calendar_timer` for schedule; an open `control-room/<kind>-<id>-*` PR → `open_proposal_exists`
   with its URL. With no worker bound the T5.3 501 stub answers unchanged.
9. **The screen stays read-only where it lives.** The git worker runs inside `control-room.service`
   (uid dave, `ProtectHome=read-only`) and writes only under `StateDirectory=control-room-proposals`
   (`/var/lib/control-room-proposals`), granted by a drop-in beside T5.3a's. `bin/workflow_pr.py
   doctor` proves the sandboxed process can fetch, commit and reach `gh` — at land, once.
10. Verify green after land; every fixture suite green on the branch; drift red on the branch is
    explained by exactly the files § Land-time steps names.

## Existing state (read, confirmed 2026-09-14)

- `git remote origin` = `https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium.git`
  (HTTPS). Pushes authenticate through `credential.https://github.com.helper=!/usr/bin/gh auth
  git-credential` in `~/.gitconfig`; `gh 2.46.0` is logged in as `Dave1524` with scopes `repo,
  workflow` (`~/.config/gh/hosts.yml`, dave 0600 — readable by every dave process already, so this
  brief grants no capability that does not exist). Repo settings: `allow_auto_merge: false`,
  `delete_branch_on_merge: false`, no rulesets. CI (`.github/workflows/verify.yml`) runs
  `bin/verify.sh` on every PR to `main` — so every PR this brief opens carries the full gate as
  evidence without the box running it.
- `bin/auto-sync` commits and pushes `main`; it **never pulls**. Merged PRs reach the box only by a
  hand `git pull --ff-only` in `~/dev/agent-workforce` (the sibling briefs' "merge to main on the
  box"). Box git identity is `Marcus (Praetorium)`; the clone here gets its own author.
- `git clone --bare` of this repo takes 0.2 s (21 MB `.git`, 469 tracked files); the join suites
  run in < 3 s total (`test_fleet_ownership` 0.3 s, `test_workflow_coverage` 0.7 s,
  `test_manifest_surfaces` 0.3 s, `test_contract_schema` 1.1 s, `test_buzz_unit_wiring` 1.6 s,
  `bin/check_deploy_drift.sh` 0.6 s, `bin/deploy --dry-run` < 1 s). A synchronous preview/submit
  inside one HTTP request is ~10-20 s; no background job is needed.
- Verified sequence for the worker (§ Architecture), against a local bare remote:
  `git clone --bare <remote> repo.git` → `git -C repo.git fetch origin
  +refs/heads/main:refs/remotes/origin/main` → `git -C repo.git worktree add --detach <work>
  refs/remotes/origin/main` → edits → `git switch -c control-room/…` → commit →
  `git push origin HEAD:refs/heads/control-room/…` → `git worktree remove --force` → `git branch -D`.
- Box timezone `Europe/Amsterdam`; `systemd-analyze calendar "Sun 09:00" --iterations=3` prints
  `Next elapse … CEST` + `(in UTC)` + `Iteration #2/#3` lines. `systemd-analyze verify <path>.timer`
  works as dave; a bad spec prints `<path>:<line>: Failed to parse calendar specification` and
  `Unit <stem>.timer has a bad unit file setting`, and it also prints unrelated `/usr/lib` warnings
  (`CPUAccounting= … ignored`) on every run — the check must filter to lines naming the unit.
- The retirement joins already in the gate, which the plan must satisfy on the branch:
  `tests/test_fleet_ownership.sh` (manifest ↔ `config/fleet-units.tsv`, both directions),
  `tests/test_manifest_surfaces.sh` (a `present = true` surface must host a live entry — W19 item
  10), `tests/test_buzz_unit_wiring.sh` (every `bin/buzz_producers.tsv` row's unit must exist in
  `systemd/`), `tests/test_workflow_coverage.py` (`timer-family-declared`: every `systemd/**/*.timer`
  outside `archive/` needs a manifest entry; `no-orphan-suite`: an unclaimed suite whose subject is
  exec'd only by an archived unit is an orphan — "moving a unit into `systemd/archive/` is the act
  that retires its script", `:520-570`), `tests/test_contract_schema.py` (grades
  `design/contracts/*.md`, non-recursive), `tests/test_workflow_registry_frozen.sh`
  (`design/workflow-registry.md` is frozen history — a retirement **does not edit it**).
- W19's chain for a headless-CC workflow (`.claude/briefs/w19-campaign-retirement-residue.md`): the
  unit execs the shared `bin/agent_propose.sh`; the real runner (`bin/run_<x>_cc.sh`) is named only
  by the manifest `runner` field and by the deny-listed `~/.config/agent-workforce/<x>.env`
  (`AGENT_RUNTIME_CMD`), whose template is `profiles/<x>.env.example`. Retiring the unit alone leaves
  that chain deployed and reachable-by-hand. The `bin/` half of `bin/check_deploy_drift.sh` has **no
  exclusion mechanism** (`runtime-only: <f> has no source` is unconditional, `:358`); only
  `bin/deploy --prune` clears it, and prune cannot be aimed (it also drops the deferred entries in
  `design/deploy-exclusions.toml`). Content trees (`profiles config docs systemd skills …`) do
  consult exclusions (`:380-424`); the unit half compares `systemd/*.{service,timer}` ↔ `/etc`
  (`maxdepth 1`, `archive/` and `user/` excluded, `:445-490`).
- `design/archive/` exists (design history); `systemd/archive/` holds six retired units;
  `profiles/archive/` five profiles. Lifecycle vocabulary `standing|campaign|spent|dormant|planned`
  (`design/agent-model.md:375-400`): `spent` = "inert clutter, should be removed" — the precedent for
  removal is the W19 commit (entry removed, dated comment left; `augustus.toml`).
- `tests/ci-expected-skips.txt` pins the SKIP set verbatim; a new box-only assertion adds exactly
  one line and a dated paragraph.
- T5.3 seam (its brief § Seams (c)): reserved for this brief — `bin/control_room_proposals.py`,
  `bin/workflow_pr_*.py`, `bin/control_room_ui/proposals.js`, `tests/test_control_room_proposals.*`,
  `tests/fixtures/control-proposals/`, and the `POST /api/v1/control/proposals` branch. T5.3's stub
  vocabulary: `{"workflow_id","kind":"schedule|retire","reason","stage":"preview|submit",
  "proposed":{…},"preview_token"}`; real responses `200 {"stage":"preview","preview_token","diff",
  "checks":[{id,status,output}],"residue":[…]}` then `200 {"stage":"submitted","pr":{"url","branch"}}`.
  T5.3's `control-room.service` carries `ProtectHome=read-only`, `ProtectSystem=full`, `User=dave`,
  and no `StateDirectory` — so the worker cannot write under `$HOME` and needs a state directory
  under `/var/lib`, exactly what a drop-in provides.

## Architecture (complete option; reasons in § Notes)

```
Mac browser ──tailnet──▶ control-room.service (dave; ProtectHome=read-only)
   proposals.js            │ bin/control_room_proposals.py  shape + peer gate + actor + HTTP map
                           ▼
                         bin/workflow_pr.py  Worker (one flock per stage)
                           │  state: /var/lib/control-room-proposals/   (StateDirectory, dave-owned)
                           │    repo.git/        bare clone of origin — never ~/dev/agent-workforce, never ~/agent-workforce
                           │    work/<pid>/      one detached worktree per proposal, removed after the stage
                           │    work/base/       pristine origin/main worktree for the drift baseline
                           │    proposals/<pid>.json (+ <pid>.diff when > 200 KiB)
                           │    gitconfig        author, credential helper, push.default=nothing
                           │    lock
                           ├─ bin/workflow_pr_git.py       fetch / worktree / diff / commit / guarded push / ls-remote
                           ├─ bin/workflow_pr_schedule.py  the schedule edit plan + description
                           ├─ bin/workflow_pr_retire.py    the retirement edit plan + subject set + retention
                           ├─ bin/workflow_retire_residue.py  W19-class scanner (source / live), CLI
                           ├─ bin/workflow_pr_checks.py    the check bundle (real suites in the worktree, shims in tests)
                           ├─ bin/workflow_pr_body.py      PR title/body + commit message (pure)
                           └─ bin/workflow_pr_record.py    proposal record shape, validate, atomic write, TTL
                           ▼
                         git push origin HEAD:refs/heads/control-room/<kind>-<id>-<stamp>   (guarded)
                         gh pr create --repo … --base main --head control-room/… --title … --body-file …  [--draft]
```

- **Not a broker action.** T5.3a's broker executes `systemctl` as root; nothing here needs root or
  touches a unit. The write target is GitHub, the credential is dave's existing `gh` login, and the
  containment property is *where* writes can land: only `control-room/*` branches on `origin`, only
  the state directory on disk. That is a property of code (`BRANCH_RE`, argv from constants,
  `push.default=nothing`) proven by tests, not of a namespace.
- **A dedicated bare clone, base `origin/main`**, never the box's live checkout: the PR must be
  against what GitHub has, and `~/dev/agent-workforce` may be ahead (uncommitted work), on a branch,
  or mid-auto-sync. The bare clone has no working tree to dirty; each proposal gets a throwaway
  worktree.
- **Synchronous stages under one `flock`**: preview and submit each hold `$STATE/lock` (timeout
  120 s → `locked`); no daemon, no queue, no state outside the record files.
- **Policy is in the worker, not the UI**: retention completeness, reason length, kind/stage
  vocabulary, check verdicts, residue verdict, token TTL and diff identity are enforced in
  `workflow_pr.py`; `proposals.js` only collects input and renders responses. The CLI mode
  (`bin/workflow_pr.py schedule|retire|list|clear|doctor`) drives the same code path.

### Request (the T5.3 seam, made concrete)

```
POST /api/v1/control/proposals        Content-Type: application/json   X-Control-Room: 1
{"workflow_id": "<logical id>", "kind": "schedule|retire", "reason": "<string>",
 "stage": "preview|submit|list", "preview_token": str|null,
 "proposed": {                                          # required for preview/submit, ignored for list
   # schedule:
   "trigger": "<unit>"|null,                            # required when the workflow has two timer triggers (augustus-content)
   "on_calendar": ["Sun 07:00", …],                     # 1..4 specs, each ^[A-Za-z0-9*,.:/ -]{1,80}$ (systemd calendar grammar; a trailing zone such as `UTC` is allowed)
   "randomized_delay_sec": "5min"|null,                 # ^\d+(s|m|min|h)?$; null = keep current
   "persistent": true|false|null,                       # null = keep current
   "manifest_trigger": str|null,                        # the manifest `trigger =` prose; null = generated "<specs joined ' / '> (+<delay> jitter)"
   "contract_trigger": str|null,                        # null = the contract's OnCalendar/RandomizedDelaySec tokens rewritten in place
   "acknowledge_pinned_tests": bool,                    # default false
   # retire:
   "artifact_retention": {"receipts": "keep|archive", "notion": "keep|archive|delete", "inbox": "keep|archive|delete", "note": str},
   "acknowledge_pinned_tests": bool}}
```

Shape rules (before any git call): unknown keys → `bad_request`; `reason` non-empty for both kinds
and ≥ 10 characters for retire; `on_calendar` may not contain `=`, `[`, newlines or exceed 80
chars; `artifact_retention` must carry all four keys with values from the vocabularies above (no
default — the decision is the point); `stage: "list"` needs only `workflow_id` and `kind`.

Actor (added by the screen, never by the client): `{"kind": "screen", "remote", "local",
"label": "dave via control-room from <remote>"}`; CLI mode: `{"kind": "cli", "user": $SUDO_USER or
login, "label": "<user> via workflow_pr.py"}`.

### Response and HTTP map

- preview → `200 {"stage": "preview", "proposal_id", "preview_token" (= proposal_id), "expires_at",
  "base": {"sha", "ref"}, "branch" (the name submit will push), "summary": str, "description": {…kind-specific, § Schedule / § Retire…},
  "files": [{"path", "change": "modified|deleted|renamed|added", "from"}], "diff": str,
  "diff_sha256", "checks": [{"id", "status": "pass|fail|warn|skip|info", "class": "hard|pinned|info",
  "output": str}], "residue": {…}|null, "retention": {…}|null, "submit_allowed": bool,
  "submit_blockers": ["checks_failed: …", "residue_in_branch: …"], "control": <fresh model.workflow_detail(id)[0]["control"]>}`
- submit → `200 {"stage": "submitted", "proposal_id", "pr": {"url", "number", "branch", "draft": bool}, "diff_sha256", "control"}`
- list → `200 {"stage": "list", "items": [records newest first, diff omitted]}`
- refusals: `unknown_workflow` 404; `peer_denied` 403; `worker_unavailable` 503 (state root
  missing/unwritable, `repo.git` absent, `gh` missing — message names `bin/workflow_pr.py doctor`);
  `failed` (a git/gh command exited non-zero after validation) 500 `{"error", "record", "branch_pushed": bool}`;
  every other refusal code 400 `{"error": {"code", "message", "choices"|null, "diff"|null}, "record"}`.
  Codes: `bad_request`, `unknown_kind`, `unknown_stage`, `not_a_timer`, `not_calendar_timer`,
  `not_standing`, `trigger_required` (with `choices`), `preview_required`, `preview_stale` (with the
  fresh `diff`), `checks_failed`, `residue_in_branch`, `retention_required`, `open_proposal_exists`
  (with `choices: [url]`), `locked`.
- `HEAD`/`GET /api/v1/control/proposals` → 405 (T5.3's rule). After **any** response
  `proposals.js` re-fetches `GET /api/v1/workflows/{id}` (T5.3's rule, kept).

### Git worker (`bin/workflow_pr_git.py`)

`GitRepo(state_root, remote_url, author, runner=subprocess)`; every argv is built from constants
plus a branch name that matched `BRANCH_RE = ^control-room/(schedule|retire)-[a-z0-9][a-z0-9-]{0,63}-\d{8}T\d{6}Z$`;
`git` runs with `GIT_CONFIG_GLOBAL=$STATE/gitconfig GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
LC_ALL=C TZ=UTC`, `--no-pager`, 60 s timeout per command (`fetch`/`push` 90 s). `$STATE/gitconfig`
is written by `init` and contains exactly: `[user] name/email` from `CONTROL_ROOM_GIT_AUTHOR`
(`Praetorium Control Room <dave.hamelink@vantagepointconsulting.nl>`), `[credential
"https://github.com"] helper = !/usr/bin/gh auth git-credential`, `[push] default = nothing`,
`[advice] detachedHead = false`, `[core] hooksPath = /dev/null` (no hook from the clone ever runs).
Methods: `init()` (bare clone if absent; refuses when `remote_url` ≠ the configured `origin`),
`fetch_main()`, `base_sha()`, `worktree_add(pid) -> path` (detached at `refs/remotes/origin/main`),
`worktree_remove(pid)`, `diff(path) -> (text, stat, files)` (`git add -A -N` then `git diff
--no-color --binary HEAD`; renames detected with `-M`), `commit(path, branch, message)`,
`push_guarded(branch)` (asserts `BRANCH_RE`, refuses `main`/anything else; argv exactly `push origin
HEAD:refs/heads/<branch>`, never `--force`), `remote_heads(prefix)` (`ls-remote --heads origin
'<prefix>*'`), `cleanup(pid, branch)`. Every call appends `{"argv", "exit", "seconds", "stderr"}`
to the stage's command log.

### Schedule plan (`bin/workflow_pr_schedule.py`, pure over a worktree path)

`plan_schedule(worktree, item, proposed, clock) -> Plan` where `item` is the read model's workflow
dict (triggers with `unit`/`scope`/`kind`, `manifestPaths`, `contract.path`, `control.state`):

1. Trigger selection: `kind == "service"` → `not_a_timer`; two timer triggers and no `trigger` →
   `trigger_required` with `choices`; `trigger` not one of the units → `bad_request`.
2. Timer file `systemd/<unit>.timer` (user scope: `systemd/user/`): parse `[Timer]` keys
   (`OnCalendar` may repeat; `OnUnitActiveSec`/`OnBootSec` present and no `OnCalendar` →
   `not_calendar_timer`), rewrite **only** the `OnCalendar=` lines (replaced by the proposed list, in
   place of the first, others removed), `RandomizedDelaySec=` (replaced or, when absent and
   proposed, inserted after the last `OnCalendar=`), `Persistent=` (same). Every other byte of the
   file is preserved; a `Description=` mentioning a weekday/time is reported as `prose` under
   `description.reviewer_attention`, never edited.
3. Manifest: in `design/agents/<owner>.toml`, inside the `[[workflows]]` block whose `unit =` matches
   (block = from its `[[workflows]]` line to the line before the next line starting with `[`), replace
   the `trigger = "…"` line's string (single-line strings only; a multi-line `trigger` →
   `bad_request` naming it). Assert with `tomllib` that the parsed document differs **only** in that
   entry's `trigger`.
4. Contract `## Trigger` section: replace every `` `OnCalendar=<current>` `` token with the proposed
   spec(s) and `` `RandomizedDelaySec=<current>` `` likewise; if the section carries no `OnCalendar=`
   token, append one line: `Schedule changed <date> (Control Room proposal <pid>):
   `OnCalendar=<spec>`.`; `contract_trigger` in the request replaces the section body verbatim.
5. `describe_schedule(current, proposed, tz, calendar_runner, control_state)` → `{"unit", "scope",
   "current": {"on_calendar", "randomized_delay_sec", "persistent", "next": [{"local", "utc"}×3]},
   "proposed": {…same…}, "timezone": {"name": "Europe/Amsterdam", "source": "timedatectl|/etc/timezone|TZ",
   "explicit_in_spec": bool}, "catch_up": str, "takes_effect": str, "reviewer_attention": [...]}`.
   Catch-up sentences: `Persistent=true and the timer is paused: a resume through the Control Room
   fires the service immediately if the stamp predates the previous elapse of the NEW schedule —
   T5.3a's resume preview shows it before applying.` / `Persistent=true and the timer is active: a
   missed elapse fires at the next daemon-reload/boot; the new schedule applies after
   `systemctl restart <unit>.timer`.` / `Persistent=false: no catch-up; …`. `takes_effect`: paused →
   `at resume (no unit is restarted by this PR)`; active → `after the land-time `restart
   <unit>.timer``.
6. Collision window: for every other `systemd/**/*.timer` (non-archive) with `OnCalendar`, the next
   three elapses via the same runner; any within ±30 min of a proposed elapse → `schedule-collisions`
   `warn` naming the unit and the shared `agent_propose.sh` flock (agent-model §6.6). Never blocking.

### Retire plan (`bin/workflow_pr_retire.py`)

`subject_set(root, item) -> Subjects`: `logical_id`, `units` (each: name, scope, `timer_path`,
`service_path`, `env_override` from the service's `Environment=AGENT_JOB_OVERRIDES=` line or
null, `run_marker` from `DELIVERY_RUN_MARKER=` or null), `manifest_paths`, `runners` (manifest
`runner` tokens resolving to `bin/` files — `runner_file()` logic from `tests/test_workflow_coverage.py:156`
— each tagged `owned` when no other **live** manifest entry names it and no non-comment line of any
live `systemd/**/*.service` or other `bin/*` file references it, else `shared`), `profiles`
(manifest `profile` when `profile_in_repo != false` and the file exists, plus
`profiles/<basename of env_override>.example` when present), `contract` (manifest `contract`,
when no other live entry names it), `suites` (manifest `suite` paths and their same-name `.py`),
`slugs` (`knowledge-digest`, `knowledge_digest`). Computed from the manifests **before** the plan
runs and stored in the `[[retired]]` record so the scanner stays self-sufficient afterwards.

`plan_retire(worktree, item, proposed, clock) -> Plan`, refusing `not_standing` unless status ∈
`standing|dormant|spent`, `not_a_timer` for `kind = "service"`, `retention_required` when the
decision is incomplete. Edits, in path order (the diff is deterministic — asserted by two runs):

1. **Manifests**: remove each `[[workflows]]` block whose `unit` is in `units`; leave in its place one
   comment: `# <unit> retired <date> via Control Room proposal <pid> (branch <branch>): <reason>.
   Artifacts: receipts=<v> notion=<v> inbox=<v>. Record: design/retired-workflows.toml.` If the
   entry's `surface` block now hosts no entry with status ∉ {spent, planned} in that manifest →
   `present = false` and a `retired = "<date>"` line added under it (S3 precedent, agent-model §3);
   remove each owned runner path from that surface's `governed_by` comma list. Assert with `tomllib`
   that the parsed workflow list shrank by exactly the removed units and no other entry changed.
   Other entries' `notes` naming the unit → reported as `prose` residue (W19 item 11), not edited.
2. **`config/fleet-units.tsv`**: drop the rows for `units`. **`bin/buzz_producers.tsv`**: drop rows
   whose unit is `<unit>.service` (the route key in `bin/buzz_routes.env` is a destination, never
   removed). **`design/deploy-exclusions.toml`**: append `[[runtime_only]]` entries (`tree`, `path`,
   `since`, `why` naming the proposal) for every deleted `profiles/` file and for the staged
   `systemd/<unit>.timer|.service` copies (the content-tree half compares
   `~/agent-workforce/systemd/`); nothing for `bin/` (no mechanism — named in the residue report).
3. **Units**: `git mv systemd/<unit>.timer systemd/archive/<unit>.timer` (+ `.service`); user scope →
   `systemd/archive/user/<unit>.*`.
4. **Runners**: `git rm` each `owned` runner; `shared` ones kept and listed (`shared, kept — still
   exec'd by <units>`). **Profiles**: `git rm` each. **Contract**: `git mv` to
   `design/archive/contracts/<name>.md` with a first line `> RETIRED <date> — Control Room proposal
   <pid>; the workflow no longer exists. Kept as history for T5.4's evidence.` **Suites**: `git rm`
   each (+ `.py`), and delete their lines from `tests/ci-expected-skips.txt` (with the paragraph
   naming them, if any, left — prose).
5. **T5.3 count literals**: in `tests/test_control_room_views.py`, module-level lines matching
   `^([A-Z][A-Z_]*)\s*=\s*(\d+)\s*(#.*)?$` whose value equals the pre-retirement standing-entry
   count or logical-workflow count (computed from the manifests, never hardcoded) are decremented by
   the entries removed / by one. When no such lines exist the coupling is caught by `pinned-tests`
   (§ Checks) instead.
6. **`design/retired-workflows.toml`**: append one `[[retired]]` with the whole subject set
   (§ Registry).
7. Residue scan over the edited worktree (`scan_source`) — the plan's own post-condition; the result
   rides in the preview as `residue.source` and refuses submit when not clear.

### Residue scanner (`bin/workflow_retire_residue.py`) — the W19 failure class, made a check

`scan_source(root, subjects) -> Report` classes, each item `{"class", "path", "line"|null, "what",
"tree", "has_check": str, "clears": "this PR|bin/deploy --prune|sudo|Dave|nothing"}`:

| class | rule | blocks `clear`? |
|---|---|---|
| `executable` | live `systemd/<unit>.*` or `systemd/user/<unit>.*` present; any non-archive `*.service` `Exec*=` line naming an owned runner; a manifest `[[workflows]]` entry with a subject unit; `runner`/`governed_by` naming an owned runner that still exists; an owned runner present in `bin/` and referenced from a non-comment line anywhere live | **yes** |
| `inert` | an owned runner or profile present but referenced by nothing live (W19's "inert is not dangerous") | source: no; live (deployed copy): **yes** |
| `files` | owned profile, env example, contract (outside `design/archive/`), suite present | **yes** |
| `declared` | `config/fleet-units.tsv` row, `bin/buzz_producers.tsv` row, `tests/ci-expected-skips.txt` line | **yes** |
| `declared-pending-prune` | `design/deploy-exclusions.toml` entries naming the subject files | no (self-clearing at prune) |
| `prose` | comment-only lines and `docs/`, `design/*.md`, manifest `notes`, unit `Description=` mentioning a slug | no — listed with file:line |

`scan_live(subjects, runtime_root, etc_dir, user_tree, systemctl_runner)`: `installed` (`/etc/systemd/system/<unit>.*`
or `~/.config/systemd/user/<unit>.*` exists; `systemctl [--user] list-unit-files <unit>.timer
<unit>.service` non-empty; `is-active` ≠ `inactive` — read-only verbs only, `--no-pager`, `TZ=UTC`),
`deployed` (`~/agent-workforce/bin/<runner>`, `~/agent-workforce/profiles/<profile|env example>`,
`~/agent-workforce/systemd/<unit>.*`), `dave-only` (the `env_override` path: **printed, never
stat'ed** — `what: "unverifiable from an agent (deny-listed); Dave runs: ls -l <path>; rm <path>"`),
`runtime-state` (`run_marker`, `~/agent-workforce/var/workflow-receipts/<id>/` — listed, never
blocking, governed by the retention decision). Verdict `clear` iff `installed` and `deployed` are
empty and (`env_override` is null or `env_removed_attested`). `render_w19_table(report)` prints
`# | residue | tree | has a check? | who clears it | how` — the W19 brief's table columns plus the
two the retirement needs. CLI: `--source ROOT --workflow ID`, `--live --workflow ID [--runtime R
--etc E --user-tree U]`, `--all` (every `[[retired]]` entry), `--json`; exit 0 clear / 1 residue /
2 unknown workflow.

### Registry (`design/retired-workflows.toml`)

Header explains: one `[[retired]]` per retired logical workflow, written by the retire plan, read by
`tests/test_workflow_retirements.sh` and `bin/workflow_retire_residue.py --all`; the subject set is
copied here because the manifest entry is gone by the time anything checks the residue. Entry:

```
[[retired]]
id = "<logical id>"                 units = ["<unit>", …]            owner = "<agent>"
retired_on = "<YYYY-MM-DD>"         reason = "<reason>"              proposal = "<pid>"
branch = "control-room/retire-<id>-<stamp>"   pr = ""                # pr filled by `clear` (the PR does not exist when this is committed)
runners = ["bin/…"]                 profiles = ["profiles/…"]        contract = "design/archive/contracts/<x>.md"|""
suites = ["tests/…"]                env_override = "~/.config/agent-workforce/<x>.env"|""
run_markers = ["/home/dave/logs/run-markers/<unit>.service"]
artifact_retention = { receipts = "keep", notion = "keep", inbox = "keep", note = "…" }
residue_cleared_on = ""             env_removed_attested = false
```

Created here with zero entries. `bin/workflow_pr.py clear <id> [--env-removed] [--pr URL]` runs
`scan_live`, refuses (exit 1, table printed) unless clear, else writes `residue_cleared_on`,
`env_removed_attested`, `pr` into the **live checkout** `~/dev/agent-workforce` — the one command in
this brief that edits the box checkout, run by Dave's hand at land, and it edits only this file;
the commit is his (`git commit -m "retire(<id>): residue cleared"` printed, not run).

### Checks (`bin/workflow_pr_checks.py`, `run_checks(worktree, kind, ctx, runner) -> list`)

Each `{"id", "class": "hard|pinned|info", "status": "pass|fail|warn|skip|info", "output"}`; `runner`
is injectable (tests fake the suite runs; the real one is `subprocess.run` with `cwd=worktree`,
120 s timeout, env = `PATH`, `HOME`, `LC_ALL=C`, `TZ=UTC` plus any `DRIFT_*`/`AGENT_WORKFORCE_RUNTIME`
already in the process env, so a fixture can redirect the drift/deploy checks).

| id | class | kind | what |
|---|---|---|---|
| `schedule-parses` | hard | schedule | `systemd-analyze calendar --iterations=3 <spec>` per proposed spec; output = the local/UTC elapses; parse error → fail |
| `unit-verify` | hard | schedule | `systemd-analyze verify <worktree>/systemd/<unit>.timer`, output filtered to lines naming the unit; `bad unit file setting` or exit ≠ 0 → fail |
| `schedule-collisions` | info | schedule | § Schedule plan 6; warn/pass |
| `manifest-joins` | hard | both | `bash tests/test_fleet_ownership.sh`, `bash tests/test_workflow_coverage.sh`, `bash tests/test_manifest_surfaces.sh`, `bash tests/test_contract_schema.sh` in the worktree; any non-zero → fail with the failing suite's `FAIL:` lines |
| `producer-join` | hard | retire | `bash tests/test_buzz_unit_wiring.sh` |
| `pinned-tests` | pinned | both | every `tests/test_*.sh` in the worktree (minus the ones the plan deleted) whose text or same-name `.py` names a subject slug or unit; each run; red ones → fail naming `file` and its `FAIL:` lines (this is where a smoke test pinning `OnCalendar=<old>` and T5.3's views fixture counts surface) |
| `residue-source` | hard | retire | `scan_source` over the worktree; any blocking item → fail |
| `drift-preview` | info | both | `bin/check_deploy_drift.sh` from the worktree vs from `work/base`; output = findings **introduced** by this branch (the expected post-merge drift: `content differs: <unit>.timer`, `runtime-only: …`, `etc-only: …`); off-box → skip |
| `deploy-preview` | info | both | `bin/deploy --dry-run` (schedule) / `bin/deploy --dry-run --prune` (retire) from the worktree; output = the itemised lines; for retire the prune list is split into `this workflow` and `also deleted by --prune (deferred exclusions)`; runtime tree absent → skip |

`submit_allowed` = no `hard` fail and (no `pinned` fail or `acknowledge_pinned_tests`) and
(retire: `residue-source` pass). Draft PR iff a `pinned` fail was acknowledged.

### PR body (`bin/workflow_pr_body.py`, pure over the record) — sections in order

Schedule: `# Schedule change: <id> (<unit>.timer)` · request line (actor, time, proposal id, reason)
· `## Current → proposed` table (`OnCalendar`, `RandomizedDelaySec`, `Persistent`, timezone + next
three elapses local/UTC for each, catch-up, takes effect, manifest trigger, contract trigger) ·
`## Diff` (fenced, the previewed bytes) · `## Checks` table · `## Reviewer attention` (prose lines,
collisions, acknowledged pinned tests as `Red on purpose until <file>:<line> …`) · `## Land
(Dave-only; this PR does none of it)`: merge (no auto-merge; `allow_auto_merge` is off) → on the box
`git -C ~/dev/agent-workforce pull --ff-only` → `bin/deploy` → `sudo cp systemd/<unit>.timer
/etc/systemd/system/ && sudo systemctl daemon-reload` → only if the timer is active: `sudo systemctl
restart <unit>.timer` (it is paused today: the schedule applies at resume) → `bash bin/verify.sh`.

Retire: `# Retire: <id>` · request line · `## Decision evidence` (from the read model: last valid
artifact, valid-artifact rate, benefit decision if the ledger has one, all `Unknown` when absent) ·
`## Artifact retention` (the three decisions + note, verbatim, and the Dave-only commands each
implies: receipts `archive` → `mv ~/agent-workforce/var/workflow-receipts/<id>
~/agent-workforce/var/workflow-receipts-retired/<id>`; Notion/inbox → Mac-side, named as such) ·
`## Removal` table (path · change · join that forces it) · `## Residue (W19 class)` — two tables:
*on this branch after the removal* (must be all non-blocking) and *on the box after merge* (the live
scan from the screen at preview time, every item with who clears it and how) · `## Checks` ·
`## Reviewer attention` · `## Land (Dave-only)`: merge → `git pull --ff-only` → `bin/deploy` (ships
`systemd/archive/`) → `sudo systemctl disable --now <unit>.timer` (a no-op while the fleet is off;
it is the retirement, not a fleet change) → `sudo rm /etc/systemd/system/<unit>.timer
/etc/systemd/system/<unit>.service && sudo systemctl daemon-reload && sudo systemctl reset-failed`
(user scope: `systemctl --user` + `~/.config/systemd/user/`) → `ls -l <env_override>` / `rm
<env_override>` → `bin/deploy --prune` **which also deletes:** `<list from deploy-preview>` →
`bin/workflow_pr.py clear <id> --env-removed --pr <url>` → commit → `bash bin/verify.sh` green.

Commit message: `control-room(<kind>): <id> — <one line>` + blank + `Requested from the Control Room
by <label> at <requested_at>.` `Proposal: <pid>` `Reason: <reason>` + the current→proposed line or
the removal list. PR title = the first line. `gh pr create --repo <owner/repo> --base main --head
<branch> --title … --body-file $STATE/work/<pid>.body.md [--draft]`; never `--fill`, never labels.

### `proposals.js` (`bin/control_room_ui/proposals.js`, vanilla, CSP `default-src 'self'`)

Loaded by one `<script src="/static/proposals.js" defer>` on the workflow page (§ Seam
deviations). On load: injects `<link rel="stylesheet" href="/static/proposals.css">` (no inline
styles — CSP), claims every `[data-proposal-kind]` button with a **capture-phase** click listener
calling `stopImmediatePropagation()` so `actions.js`'s generic poster never sees them (no edit to
`actions.js`), and POSTs `stage: "list"` to render `<ul id="proposal-list">` (PR links) under the
Controls panel. Click → a `<dialog id="proposal-dialog">` built by the script: schedule form
(`OnCalendar` text with the current value prefilled, delay, persistent checkbox, reason) / retire
form (reason, three retention `<select>`s with no default option selected, note) → `Preview` →
the dialog shows the summary line, description table, `<pre>` diff, checks table, residue tables and
`submit_blockers` → `Open pull request` (disabled unless `submit_allowed`; a pinned-only red shows a
checkbox "I acknowledge these tests go red on the branch; open as draft") → `confirm("Open the
pull request with exactly this diff?")` → POST `stage: "submit"` with the token → renders `pr.url`
as a link and the summary into `#control-result` (first line `submitted · <kind> · <id> · PR #N`),
then re-fetches `GET /api/v1/workflows/{id}`. Every JSON response also lands in `#control-result`.
Refusals render `code · message` first.

## Files to modify

- `bin/control_room_api.py` — **one edit site** (the seam): the `POST /api/v1/control/proposals`
  branch → `control_room_proposals.handle_post(self, getattr(type(self), "proposals", None), self.model)`;
  plus, in `main()`, `proposals = control_room_proposals.ProposalsControl.from_env()` and
  `server.RequestHandlerClass.proposals = proposals` (the same binding pattern T5.3a uses for
  `control`; a second edit site, § Seam deviations 1). `import control_room_proposals` beside the
  sibling imports. Nothing else.
- `bin/control_room_view_workflow.py` — one line: `<script src="/static/proposals.js" defer></script>`
  after the Controls panel (§ Seam deviations 2).
- `design/fleet-suites.toml` — five `[[suite]]` entries (owner `fleet`, one-sentence
  `why_no_workflow`) naming the anchored ids in § Test plan.
- `tests/ci-expected-skips.txt` — one line + a dated paragraph:
  `SKIP: test_workflow_retirements.sh — the deployed trees a live residue scan reads (absent: ~/agent-workforce/bin ~/agent-workforce/systemd)`.
- `docs/runbook.md` — `## Control Room proposals (T5.3b)` after T5.3a's section: the two flows, the
  state root, `doctor`/`init`/`clear`, the land sequences for both PR kinds, "prune cannot be
  aimed", "the fleet stays off — a schedule change applies at resume".
- `CLAUDE.md` (repo) § Where things live — one bullet: schedule changes and retirements are
  `control-room/*` PRs from `/var/lib/control-room-proposals/repo.git`, never edits; the retire
  registry and `bin/workflow_retire_residue.py --live` are the fail-closed half.

## Files to create

Source (stdlib only, `from __future__ import annotations`, Python 3.11+; sibling imports via
`sys.path.insert(0, dirname(__file__))` as `control_room_api.py` does; keep each under ~300 lines):

- `bin/control_room_proposals.py` — `handle_post`, `validate_shape`, `peer_allowed` (the same
  8-line rule as T5.3a's; duplicated deliberately so this brief does not import T5.3a's file),
  `stub_response` (T5.3's 501, kept when `proposals is None`), `HTTP_STATUS_BY_CODE`,
  `ProposalsControl.from_env()` (`CONTROL_ROOM_PROPOSALS_ROOT`, default
  `~/agent-workforce/var/control-proposals` for a loopback dev instance; `CONTROL_ROOM_PROPOSALS_REMOTE`;
  `CONTROL_ROOM_GIT_AUTHOR`; `CONTROL_ROOM_GH_REPO`, default `Dave1524/Hermes_Agent_Workforce_Praetorium`).
- `bin/workflow_pr.py` — `Worker(state_root, remote, gh_repo, author, clock, runner, tz_reader,
  calendar_runner)`, `preview(request, item, model_ctx)`, `submit(...)`, `list(workflow_id, kind)`,
  `doctor()`, `init()`, `clear(...)`; CLI `schedule <id> --on-calendar S [--delay D]
  [--persistent yes|no] [--trigger U] --reason R [--preview|--submit TOKEN]`, `retire <id> --reason R
  --receipts V --notion V --inbox V --note N [--preview|--submit TOKEN]`, `list <id>`, `doctor`,
  `init`, `clear <id> [--env-removed] [--pr URL]`; `--state`, `--remote`, `--now` (tests).
  `PREVIEW_TTL_SECONDS = 1800`, `LOCK_TIMEOUT_SECONDS = 120`, `STAGE_BUDGET_SECONDS = 300`.
- `bin/workflow_pr_git.py` — § Git worker. `BRANCH_RE`, `GitRepo`, `GitFailed`.
- `bin/workflow_pr_schedule.py` — § Schedule plan. `plan_schedule`, `parse_timer`, `render_timer`,
  `rewrite_manifest_trigger`, `rewrite_contract_trigger`, `describe_schedule`, `collisions`,
  `SPEC_RE`, `DELAY_RE`, `COLLISION_WINDOW_SECONDS = 1800`.
- `bin/workflow_pr_retire.py` — § Retire plan. `subject_set`, `plan_retire`, `remove_manifest_block`,
  `flip_empty_surface`, `prune_governed_by`, `drop_tsv_rows`, `append_exclusions`, `archive_unit`,
  `archive_contract`, `decrement_count_literals`, `append_retired_record`, `validate_retention`,
  `RETENTION_VOCAB`.
- `bin/workflow_retire_residue.py` — § Residue scanner. `scan_source`, `scan_live`, `verdict`,
  `render_w19_table`, `CLASSES`, `main`.
- `bin/workflow_pr_checks.py` — § Checks. `run_checks`, `CHECKS` (ordered), `submit_allowed`,
  `JOIN_SUITES`, `find_pinned_suites`, `drift_introduced`.
- `bin/workflow_pr_body.py` — § PR body. `title`, `body`, `commit_message`.
- `bin/workflow_pr_record.py` — record schema 1 (`proposal_id = "<%Y%m%dT%H%M%SZ>-<kind>-<id>-<6 hex>"`;
  keys: `schema, proposal_id, kind, workflow_id, stage, actor, reason, requested_at, completed_at,
  base{remote,ref,sha}, branch, files[], diff_sha256, diff_stat, diff|diff_path, description,
  checks[], residue, retention, pr, refusal, commands[]`), `validate_record`, `write` (tmp + fsync +
  rename, 0644), `load`, `newest(state, workflow_id, kind)`, `token_valid(record, now)`.
- `bin/control_room_ui/proposals.js`, `bin/control_room_ui/proposals.css` — § proposals.js
  (dialog, tables, `.blocker` red, `.draft` amber; dark-scheme variant; works at 400 px).
- `systemd/control-room.service.d/proposals.conf` — exact content:

```
# T5.3b (2026-09-14): the screen gets a writable state directory for the schedule/retirement
# PR worker — a bare clone of origin and the proposal records — because control-room.service
# runs ProtectHome=read-only and must keep doing so. Nothing here widens the screen's reach:
# writes land in /var/lib/control-room-proposals and on control-room/* branches of origin only.
# Land: sudo mkdir -p /etc/systemd/system/control-room.service.d
#   && sudo cp systemd/control-room.service.d/proposals.conf /etc/systemd/system/control-room.service.d/
#   && sudo systemctl daemon-reload && sudo systemctl restart control-room.service   (the screen; no workflow timer)
[Service]
StateDirectory=control-room-proposals
Environment=CONTROL_ROOM_PROPOSALS_ROOT=/var/lib/control-room-proposals
Environment=CONTROL_ROOM_PROPOSALS_REMOTE=https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium.git
Environment=CONTROL_ROOM_GH_REPO=Dave1524/Hermes_Agent_Workforce_Praetorium
Environment=CONTROL_ROOM_GIT_AUTHOR=Praetorium Control Room <dave.hamelink@vantagepointconsulting.nl>
Environment=GH_NO_UPDATE_NOTIFIER=1
Environment=GH_PROMPT_DISABLED=1
Environment=GIT_TERMINAL_PROMPT=0
```

- `design/retired-workflows.toml` — § Registry header, zero entries.
- `tests/acceptance/control_room_proposals.sh` — hand-run acceptance (§ Hand-run acceptance);
  `set -uo pipefail`, shellcheck-clean, not under `tests/*.sh`; contains no `--submit`, no
  `"stage":"submit"`, no `gh pr`, no `push` (self-checked by grep before it starts).

Fixtures (`tests/fixtures/control-proposals/`, committed; suites copy what they mutate into a temp dir):

- `bin/gh` — Python shim: `auth status` → exit 0; `pr list --json … --state open` → the JSON in
  `FAKE_GH_PR_LIST` (default `[]`); `pr create …` → records argv + the `--body-file` contents to
  `FAKE_GH_LOG`, prints `https://github.com/fixture/repo/pull/<n>` (counter), exit 0; `FAKE_GH_FAIL=create`
  → exit 1 with stderr `fake gh: refused`; anything else → exit 2.
- `bin/systemd-analyze` — Python shim: `calendar --iterations=N <spec>` prints the real layout from
  `FAKE_CALENDAR` (spec → list of ISO local times; UTC derived with `zoneinfo` `Europe/Amsterdam`);
  unknown spec → exit 1 `Failed to parse calendar specification`; `verify <path>` → exit 1 with
  `<path>:4: Failed to parse calendar specification` + `Unit <stem> has a bad unit file setting`
  when the file's `OnCalendar` is not in `FAKE_CALENDAR`, else exit 0 printing one unrelated
  `/usr/lib/systemd/system/x.slice:1: Support for option CPUAccounting= has been removed` line (the
  filter must drop it).
- `bin/systemctl` — Python shim for the live scan: `list-unit-files <names>` and `is-active` from
  `FAKE_SYSTEMCTL_STATE` (unit → present/active flags); logs argv to `FAKE_SYSTEMCTL_LOG`; any
  mutating verb → exit 2 `fake systemctl: refused` (the scanner must never send one — asserted).
- `repo/` — the **synthetic mini-repo** (committed files; suites `git init` it into a temp dir,
  commit, then `git clone --bare` it as the fixture remote): `design/agents/{claudius,trajan}.toml`
  (three standing timer workflows: `alpha` — owned runner `bin/run_alpha_cc.sh`, profile
  `profiles/alpha_task.md`, `profiles/alpha.env.example`, contract, suite `tests/test_alpha_smoke.sh`
  pinning `OnCalendar=Sun 09:00`, producer row, unit `Environment=AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/alpha.env`,
  `DELIVERY_RUN_MARKER=`; `beta` — shares `bin/agent_propose.sh` (the shared runner, exec'd by both
  units) and is the surface's other occupant; `gamma` — two triggers `gamma` + `gamma-dispatch`
  folded by `logical_workflow`, both producer rows), one `kind = "service"` entry, one
  `OnUnitActiveSec` timer (`refresh`), `[surfaces.scheduled]` with `governed_by` naming both runners,
  a `notes` in `beta` mentioning `alpha` (prose residue), `config/fleet-units.tsv`,
  `bin/buzz_producers.tsv` + `bin/buzz_routes.env`, `design/deploy-exclusions.toml` (one unrelated
  deferred entry), `design/contracts/*.md`, `systemd/*.timer|.service` + `systemd/archive/.keep`,
  `tests/ci-expected-skips.txt` with a line for `test_alpha_smoke.sh`, a stand-in
  `tests/test_control_room_views.py` with `STANDING_ENTRIES = 5` / `LOGICAL_WORKFLOWS = 4`
  (the fixture's true counts, computed in the test to assert the decrement), and a stand-in
  `tests/test_views_no_constants.py` variant selected by a test knob, `docs/runbook.md` naming
  `alpha` in a table row.
- `runtime/` — a fixture runtime tree (`bin/agent_propose.sh` executable so `bin/deploy`'s guard
  passes, `bin/run_alpha_cc.sh`, `profiles/alpha_task.md`, `profiles/alpha.env.example`,
  `systemd/alpha.timer`, `systemd/deferred.service` — the "also deleted by prune" case); `etc/`
  with `alpha.timer`/`alpha.service`; `user/` empty; `deny/agent-workforce/alpha.env` — **exists on
  purpose**, to prove the scanner reports it `unverifiable` without stat'ing it (the test monkeypatches
  `os.stat`/`pathlib.Path.exists` inside the scanner module to raise on that path).
- `w19/` — a second mini-tree reproducing the W19 chain (two campaign shims, the shared topic
  runner, two profiles, registry rows in a frozen md, an `augustus.toml` with the empty surface and
  the collision note) — the regression fixture for `::residue-w19-table`.

Tests (one `.sh` wrapper per `.py`, `python3 tests/<name>.py`, exactly `tests/test_contract_exec.sh`'s
shape; anchors live in the `.py`):

- `tests/test_control_room_proposals.{sh,py}` (the `.sh` also lints `tests/acceptance/control_room_proposals.sh`
  and greps `bin/control_room_ui/proposals.js`)
- `tests/test_workflow_pr_schedule.{sh,py}`
- `tests/test_workflow_pr_retire.{sh,py}`
- `tests/test_workflow_retire_residue.{sh,py}`
- `tests/test_workflow_retirements.{sh,py}` (the registry consumer; the `.sh` carries the box predicate)

## Test plan (TDD: each red first; ids are the `(::id)` anchors and the fleet-suites `asserts`)

Common harness (`tests/test_control_room_proposals.py` exports it; the other suites import it):
`make_remote(tmp, src=FIXTURES/"repo") -> (remote_bare, seed_sha)`; `make_worker(tmp, remote, now)`
with `PATH=<FIXTURES/bin>:$PATH`, `FAKE_*` env, `tz_reader=lambda: "Europe/Amsterdam"`, and the
suite-running checks faked by a `FakeRunner` that records argv and returns exit 0 unless told
otherwise; `snapshot_repo(tmp)` — for one realism test, copies the real checkout's
`git ls-files --cached --others --exclude-standard` set into a temp dir, `git init` + commit, and
uses **that** as the remote (never a clone of the live checkout's history, never `origin`). Every
`git`/`gh` call in every test goes to a temp remote; the suites assert `origin` is never named by
comparing the remote URL in every recorded argv against the temp path.

`tests/test_control_room_proposals.py`
- (::proposal-preview-before-pr) `preview schedule alpha` `Sun 07:00` → 200 with `diff`,
  `diff_sha256`, `checks`, `preview_token`, `submit_allowed`; the temp remote has **no**
  `control-room/*` head; `FAKE_GH_LOG` is empty; the record is `previewed`; `work/<pid>` is gone.
- (::proposal-submit-needs-fresh-preview) submit without token → `preview_required`; token from a
  preview, then a commit on the remote's `main` that changes `systemd/alpha.timer` → submit refused
  `preview_stale` with the new diff, nothing pushed; token issued 31 min earlier (`--now`) →
  `preview_stale`; a commit on `main` that touches an unrelated file → submit **succeeds** (same
  diff bytes on a new base) and the record's `base.sha` is the new one; on success the remote has
  `control-room/schedule-alpha-<stamp>`, `git diff main..<branch>` there equals the previewed diff
  byte-for-byte, `FAKE_GH_LOG` shows `pr create --repo … --base main --head <branch> --title … --body-file …`
  and the body carries the § PR body sections, response `pr.url`, record `submitted`, worktree removed,
  local branch deleted.
- (::proposal-never-touches-main-or-runtime) sha256 of every file under the fixture runtime tree
  and under a copy standing in for `~/dev/agent-workforce` before and after preview+submit are
  identical; every recorded `push` argv is exactly `["git", "push", "origin", "HEAD:refs/heads/control-room/…"]`;
  `push_guarded("main")`, `("refs/heads/main")`, `("control-room/../x")`, `("control-room/schedule-x-20260914T080000Z ")`
  raise; `BRANCH_RE` rejects them; grep over `bin/control_room_proposals.py bin/workflow_pr*.py
  bin/workflow_retire_residue.py`: no `pr merge`, no `--force`, no `deploy` argv without `--dry-run`,
  no `systemctl` with `enable|disable|start|stop|restart`, no `~/dev/agent-workforce` literal except
  in `clear`.
- (::proposal-refusals-and-status-map) unknown id → 404; `kind: "rm"` → 400 `unknown_kind`;
  `stage: "merge"` → 400; missing header → 400; non-JSON → 400; `workflow_id: "../x"` → 400;
  `kind = service` entry → `not_a_timer`; `refresh` (OnUnitActiveSec) schedule → `not_calendar_timer`;
  `gamma` schedule without `trigger` → `trigger_required` with `choices == ["gamma", "gamma-dispatch"]`;
  actor `remote == local` → 403 `peer_denied`; `remote: "127.0.0.1", local: "100.86.82.16"` → 403;
  `local: "127.0.0.1"` → allowed; `FAKE_GH_PR_LIST` with an open `control-room/schedule-alpha-…` →
  `open_proposal_exists` with the URL; `FAKE_GH_FAIL=create` → 500 `failed`, record names the pushed
  branch and `branch_pushed: true`; state root removed → 503 `worker_unavailable` naming `doctor`;
  with `proposals=None` bound the T5.3 stub answers 501 `{"status":"not_implemented",…}` and unknown
  id → 404 (T5.3's `::control-room-control-stub-501` still passes — run it).
- (::proposal-every-outcome-recorded) one record per request across previewed / submitted /
  refused / failed; `validate_record(data) == []` for each; `commands[]` lists every git and gh
  argv with `exit`; two previews started concurrently against one state root → serialised (command
  logs do not interleave; one may be `locked` only if the first exceeds the timeout — assert either
  both succeed in sequence or the second is `locked`, never two worktrees at once); no `*.tmp` left.
- (::proposal-list-stage) after the above, `stage: "list"` for `alpha` returns the records newest
  first without `diff`, and the command log for that request is empty (no git call).
- (::proposals-js-flow) grep-level over `proposals.js`: `data-proposal-kind`, `capture`,
  `stopImmediatePropagation`, `"stage":"preview"`, `"stage":"submit"`, `"stage":"list"`,
  `preview_token`, `artifact_retention`, `acknowledge_pinned_tests`, `confirm(`, `<dialog`,
  `proposals.css`, no `style=`, and `` `/api/v1/workflows/${` `` (the re-fetch).
- (::proposal-doctor) `doctor` against the fixture → every line `ok`; with `repo.git` removed →
  `fail: repo.git missing — run: bin/workflow_pr.py init`; with `PATH` lacking `gh` → fail names it;
  exit 1 on any fail.
- (::proposal-realism-snapshot) `snapshot_repo` remote: `preview schedule knowledge-digest "Sun 07:00"`
  with the **real** `JOIN_SUITES` runner → `manifest-joins` pass, `unit-verify` pass (shim),
  `pinned-tests` runs `tests/test_knowledge_digest_smoke.sh` (names the unit) and reports its
  status; the diff touches exactly `systemd/knowledge-digest.timer`, `design/agents/claudius.toml`
  (one `trigger` line) and `design/contracts/knowledge-digest.md` (the `## Trigger` tokens).

`tests/test_workflow_pr_schedule.py`
- (::schedule-diff-is-exact) `alpha` `Sun 07:00` → files = exactly the timer, the manifest, the
  contract; the timer differs on the `OnCalendar=` line only; `tomllib` before/after differs only in
  `alpha.trigger`; the contract's `## Trigger` carries `` `OnCalendar=Sun 07:00` `` and nothing
  else changed; two runs produce identical bytes.
- (::schedule-describes-tz-and-catch-up) description: `timezone.name == "Europe/Amsterdam"`, three
  `next` entries with `local` ending `CEST|CET` and `utc` ending `UTC` for current and proposed;
  `Persistent=true` + `control.state == "paused"` → `catch_up` names `resume` and T5.3a;
  `persistent: false` proposed → `no catch-up`; `control.state == "active"` → `takes_effect`
  names `restart alpha.timer`; a spec ending ` UTC` → `explicit_in_spec: true`.
- (::schedule-refuses-bad-spec) `Funday 25:00` → `schedule-parses` fail, `unit-verify` fail (shim),
  `submit_allowed False`, submit → `checks_failed`; `Sun 09:00=x` / a 90-char spec / a spec with a
  newline → `bad_request` and the command log is empty.
- (::schedule-collision-window) `FAKE_CALENDAR` placing `beta` 10 min after the proposed elapse →
  `schedule-collisions` warn naming `beta.timer` and `agent_propose.sh`; 2 h apart → pass.
- (::schedule-pinned-tests-named) `alpha`'s smoke suite pins `OnCalendar=Sun 09:00` → `pinned-tests`
  fail naming `tests/test_alpha_smoke.sh`; submit → `checks_failed` listing it; with
  `acknowledge_pinned_tests: true` → submitted, `gh pr create` argv carries `--draft`, the body has
  `Red on purpose until tests/test_alpha_smoke.sh`.
- (::schedule-multi-trigger) `gamma` with `trigger: "gamma-dispatch"` → only that timer and that
  entry's `trigger` line change; `trigger: "sshd"` → `bad_request`.
- (::schedule-randomized-and-persistent) `randomized_delay_sec: "10min"` on a timer without the key
  → inserted after the last `OnCalendar=`; `persistent: false` → `Persistent=false` rewritten in
  place; null values leave the lines byte-identical.

`tests/test_workflow_pr_retire.py`
- (::retire-removal-across-joins) `retire alpha` → the diff: manifest block gone and one dated
  comment in its place, `tomllib` shows exactly one fewer entry and no other entry changed;
  `[surfaces.scheduled]` still `present = true` (beta remains) and `governed_by` lost
  `bin/run_alpha_cc.sh` only; fleet-units row gone; producers row gone; `bin/buzz_routes.env`
  untouched; `systemd/alpha.timer` + `.service` renamed into `systemd/archive/`;
  `bin/run_alpha_cc.sh`, `profiles/alpha_task.md`, `profiles/alpha.env.example`,
  `tests/test_alpha_smoke.sh` deleted; the `ci-expected-skips.txt` line gone; contract renamed to
  `design/archive/contracts/alpha.md` with the `> RETIRED` first line; `design/deploy-exclusions.toml`
  gained four `[[runtime_only]]` entries (two `profiles`, two `systemd`) each naming the proposal;
  `design/retired-workflows.toml` gained one `[[retired]]` with the full subject set and
  `pr = ""`; `STANDING_ENTRIES`/`LOGICAL_WORKFLOWS` decremented by 1; `docs/runbook.md` untouched
  and its row listed as `prose`; two runs → identical bytes.
- (::retire-keeps-shared-runner) `bin/agent_propose.sh` kept and listed `shared, kept — still exec'd
  by beta.service`; retiring `beta` afterwards (its only remaining user) would make it owned —
  asserted by `subject_set` on the post-alpha tree.
- (::retire-empties-a-surface) retire `alpha` **and** `beta` (two proposals in sequence on the same
  remote) → after the second, `[surfaces.scheduled]` reads `present = false` with a `retired =`
  line, `governed_by` empty string, and the real `tests/test_manifest_surfaces.sh` (copied into the
  fixture repo for this test) passes on the result.
- (::retire-needs-explicit-retention) missing `artifact_retention` → `retention_required`; missing
  `note` or `inbox` → `retention_required` naming the key; `receipts: "delete"` → `bad_request`
  (not in vocabulary); valid → verbatim in the record, the `[[retired]]` entry and the PR body.
- (::retire-two-trigger-retires-both) `gamma` → both units archived, both producer rows gone, both
  fleet-units rows gone, one `[[retired]]` with `units == ["gamma", "gamma-dispatch"]`.
- (::retire-count-literals-or-pinned) with the constants stand-in → decremented and `pinned-tests`
  pass; with the no-constants variant → `pinned-tests` fail naming `tests/test_views_no_constants.py`
  and submit needs `acknowledge_pinned_tests` (draft PR).
- (::retire-pr-body-sections) the body has, in order, `## Decision evidence`, `## Artifact
  retention`, `## Removal`, `## Residue (W19 class)` with both tables and the six columns,
  `## Checks`, `## Reviewer attention`, `## Land (Dave-only`; it names `bin/deploy --prune` and lists
  `systemd/deferred.service` under "also deleted", the `sudo rm /etc/systemd/system/alpha.timer`
  line, `ls -l ~/.config/agent-workforce/alpha.env`, `workflow_pr.py clear alpha`; it contains no
  `enable --now` and no `systemctl start`.
- (::retire-refusals) `kind = service` → `not_a_timer`; a `planned` entry → `not_standing`;
  `reason: "x"` → `bad_request` (< 10 chars); `spent` entry (`nekovri`-shaped, `contract_exempt`) →
  plan succeeds with `contract = ""` (nothing to archive).

`tests/test_workflow_retire_residue.py`
- (::residue-source-classes) over `repo/` with `alpha`'s subject set (nothing removed): every class
  appears exactly as § Residue's table says (unit files, manifest entry, `governed_by`, Exec line
  → `executable`; profile/env example/contract/suite → `files`; tsv rows + ci-skip line →
  `declared`; the `beta` note + runbook row → `prose`); after `plan_retire` the same scan reports
  only `prose` and `declared-pending-prune`, verdict `clear`; a runner present but referenced by
  nothing → `inert` (non-blocking in source).
- (::residue-fails-closed-on-branch) after `plan_retire`, restore `systemd/alpha.timer` in the
  worktree by hand → `submit` refused `residue_in_branch` naming `systemd/alpha.timer`, nothing
  pushed, record `refused`.
- (::residue-live-fails-closed) `scan_live` with the fixture `etc/` holding `alpha.timer` → `installed`
  item, `who clears: sudo`, the exact `rm` + `daemon-reload` line, exit 1; `FAKE_SYSTEMCTL_STATE`
  listing `alpha.timer` → `installed` via `list-unit-files`; runtime holding `bin/run_alpha_cc.sh`
  → `deployed`, `who clears: bin/deploy --prune`; everything removed but `env_removed_attested`
  false → still exit 1 with the `dave-only` item; with `--env-removed` → exit 0 `clear`; the
  `deny/agent-workforce/alpha.env` fixture exists and the scanner's stat hook is patched to raise
  on it — it is still reported `unverifiable from an agent`, never `present`/`absent`; the systemctl
  log carries only `list-unit-files`/`is-active` argv.
- (::residue-w19-table) the `w19/` fixture with the two campaigns' subject set → the table
  reproduces W19's eleven rows by class (`executable` for the three shims/runner while the unit is
  live, `files` for the two profiles, `prose` for the registry rows and the collision note,
  `declared` for `[surfaces.scheduled]` `governed_by`), and after removing the units alone (the
  historical commit) the verdict is **not** clear — the check that did not exist on 2026-09-04.
- (::residue-cli) `--source ROOT --workflow alpha` exit 1 with the table; `--workflow nope` exit 2;
  `--json` parses and carries `verdict`.

`tests/test_workflow_retirements.py` (+ `.sh` with `box_only_with "the deployed trees a live
residue scan reads" ~/agent-workforce/bin ~/agent-workforce/systemd` guarding **only** group 2)
- (::retired-registry-clean-source) group 1, every checkout: for each `[[retired]]` in
  `design/retired-workflows.toml` the required keys are present and typed, `artifact_retention`
  complete, and `scan_source(ROOT, subjects)` has no blocking item; zero entries → prints `checked 0
  retired entries (registry created empty, T5.3b)` and passes; a synthetic registry with a
  half-retired entry (unit still live in a temp copy of `systemd/`) → red naming it.
- (::retired-registry-live-clean) group 2, box only: entries with `residue_cleared_on` set →
  `scan_live` must be clear (the W19 "units came back" guard); entries without it → **FAIL** naming
  each pending item and the `clear` command (fail closed — the same red the drift check already
  shows post-merge, with names); zero entries → passes.

Fleet registry: five `[[suite]]` entries in `design/fleet-suites.toml` naming exactly the ids
above; `tests/test_workflow_coverage.py`'s asserts join fails on any id missing from either side.

## Implementation steps (ordered; commit after each numbered group — the auto-sync sweep runs every 15 min; work in a worktree, never the canonical checkout's `main`)

1. Fixtures first: `tests/fixtures/control-proposals/{bin/gh,bin/systemd-analyze,bin/systemctl,repo/**,runtime/**,etc/**,w19/**}`.
   Prove the shims by hand (`FAKE_CALENDAR=… bin/systemd-analyze calendar --iterations=3 "Sun 07:00"`;
   `FAKE_GH_LOG=/tmp/x bin/gh pr create --title t --body-file /dev/null`). `git init` the mini-repo in a
   temp dir and run the real `tests/test_fleet_ownership.sh` against it once to confirm the fixture
   manifests and `fleet-units.tsv` agree (they must, or every join check in the suites is testing a
   broken fixture).
2. `bin/workflow_pr_record.py` + `bin/workflow_pr_git.py` and the harness in
   `tests/test_control_room_proposals.py`: `::proposal-never-touches-main-or-runtime` (the guard
   first), `::proposal-every-outcome-recorded` (record + validate).
3. `bin/workflow_pr_schedule.py` + `tests/test_workflow_pr_schedule.{sh,py}` in the order
   `::schedule-diff-is-exact` → `::schedule-refuses-bad-spec` → `::schedule-randomized-and-persistent`
   → `::schedule-multi-trigger` → `::schedule-describes-tz-and-catch-up` → `::schedule-collision-window`
   → `::schedule-pinned-tests-named` (needs step 4's checks — write the check bundle's schedule half
   here).
4. `bin/workflow_pr_checks.py` (all check ids; the suite-running ones behind `runner`) and
   `bin/workflow_pr_body.py`; `bin/workflow_pr.py` `preview`/`submit`/`list`/`doctor`/`init`;
   then `::proposal-preview-before-pr` → `::proposal-submit-needs-fresh-preview` →
   `::proposal-refusals-and-status-map` → `::proposal-list-stage` → `::proposal-doctor`.
5. `bin/workflow_retire_residue.py` + `tests/test_workflow_retire_residue.{sh,py}`:
   `::residue-source-classes` → `::residue-w19-table` → `::residue-live-fails-closed` → `::residue-cli`.
6. `bin/workflow_pr_retire.py` + `tests/test_workflow_pr_retire.{sh,py}` in the order
   `::retire-needs-explicit-retention` → `::retire-removal-across-joins` → `::retire-keeps-shared-runner`
   → `::retire-two-trigger-retires-both` → `::retire-empties-a-surface` → `::retire-count-literals-or-pinned`
   → `::retire-refusals` → `::retire-pr-body-sections`; then `::residue-fails-closed-on-branch`
   (retire through the worker) and `clear` in `workflow_pr.py`.
7. `design/retired-workflows.toml` (empty) + `tests/test_workflow_retirements.{sh,py}`; add the
   `ci-expected-skips.txt` line and paragraph.
8. `bin/control_room_proposals.py` + the one seam edit in `bin/control_room_api.py` (+ the
   `main()` binding) → `::proposal-refusals-and-status-map`'s HTTP half over T5.3's fixture helper
   (`tests/control_room_fixture.py`, `127.0.0.1:0`); run `bash tests/test_control_room_api.sh` and
   `bash tests/test_control_room_views.sh` — T5.3's stub test must still pass unchanged.
9. `bin/control_room_ui/proposals.{js,css}` + the one-line `<script>` in
   `bin/control_room_view_workflow.py` + `::proposals-js-flow`; `::proposal-realism-snapshot`.
10. `systemd/control-room.service.d/proposals.conf` (verbatim); `tests/acceptance/control_room_proposals.sh`;
    `design/fleet-suites.toml` entries; `docs/runbook.md` section; `CLAUDE.md` bullet.
11. Run every touched suite directly (`bash tests/test_control_room_proposals.sh`, `bash
    tests/test_workflow_pr_schedule.sh`, `bash tests/test_workflow_pr_retire.sh`, `bash
    tests/test_workflow_retire_residue.sh`, `bash tests/test_workflow_retirements.sh`, `bash
    tests/test_control_room_api.sh`, `bash tests/test_control_room_views.sh`, `bash
    tests/test_workflow_coverage.sh`, `bash tests/test_fleet_ownership.sh`, `bash
    tests/test_deploy_drift.sh`) — all green on the branch. Then `bash bin/verify.sh`: the **only**
    red is drift naming this brief's `bin/` files, `bin/control_room_ui/proposals.{js,css}`, the
    modified `control_room_api.py` / `control_room_view_workflow.py` (source ≠ runtime until
    `bin/deploy`) and `control-room.service.d/proposals.conf` (source-only in `/etc`).
12. Loopback smoke, no unit, no root, no origin: `mkdir -p /tmp/crp && git clone --bare
    ~/dev/agent-workforce /tmp/crp-remote.git` (a **local** stand-in for origin — the worker's
    remote is this path, so nothing reaches GitHub) → `CONTROL_ROOM_PROPOSALS_ROOT=/tmp/crp
    CONTROL_ROOM_PROPOSALS_REMOTE=/tmp/crp-remote.git python3 bin/workflow_pr.py init && … doctor`
    (expect `fail` only on `gh auth` if the shim is not on PATH — put `tests/fixtures/control-proposals/bin`
    first on PATH for the smoke) → `python3 bin/workflow_pr.py schedule knowledge-digest --on-calendar
    "Sun 07:00" --reason smoke --preview` prints the diff, the description and the checks; run the
    screen on loopback with the same env plus `CONTROL_ROOM_RECEIPT_ROOT=tests/fixtures/control-room/receipts`
    and `curl -s -X POST http://127.0.0.1:8788/api/v1/control/proposals -H 'X-Control-Room: 1' -H
    'Content-Type: application/json' -d '{"workflow_id":"knowledge-digest","kind":"schedule","reason":"smoke","stage":"preview","proposed":{"on_calendar":["Sun 07:00"]}}'`
    → 200 with `diff` and `preview_token`; `-d '{"workflow_id":"nope","kind":"retire","stage":"preview"}'`
    → 404 with a record under `/tmp/crp/proposals/`. Stop the screen; `rm -rf /tmp/crp /tmp/crp-remote.git`.
    Nothing on the box changed and nothing left the box.

## Land-time steps (sudo; the branch cannot be green before these — say so in the PR, do not soften the gate)

1. Merge to `main` on the box (`git pull --ff-only` after the GitHub merge); `bin/deploy` (ships
   `bin/`, `bin/control_room_ui/`, `systemd/` including the drop-in). `bin/deploy` exits non-zero
   while `/etc/systemd/system/control-room.service.d/proposals.conf` is missing — expected.
2. `sudo mkdir -p /etc/systemd/system/control-room.service.d && sudo cp
   systemd/control-room.service.d/proposals.conf /etc/systemd/system/control-room.service.d/ &&
   sudo systemctl daemon-reload && sudo systemctl restart control-room.service` — the screen picking
   up its drop-in; **no workflow timer is touched.** (If T5.3a has landed, its `broker.conf` sits
   beside this one; both apply.)
3. `ls -ld /var/lib/control-room-proposals` → `drwxr-xr-x dave dave` (created by `StateDirectory=`).
   Then, as dave from a shell: `CONTROL_ROOM_PROPOSALS_ROOT=/var/lib/control-room-proposals
   python3 ~/agent-workforce/bin/workflow_pr.py init` (the bare clone of origin, ~0.5 s).
4. Prove the sandbox can do the work — the step that answers "does `ProtectHome=read-only` break
   git or gh":
   `sudo systemd-run --uid=dave --gid=dave -p ProtectHome=read-only -p ProtectSystem=full -p StateDirectory=control-room-proposals -E HOME=/home/dave -E CONTROL_ROOM_PROPOSALS_ROOT=/var/lib/control-room-proposals -E CONTROL_ROOM_PROPOSALS_REMOTE=https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium.git -E GH_NO_UPDATE_NOTIFIER=1 --wait --pipe --collect /usr/bin/python3 /home/dave/agent-workforce/bin/workflow_pr.py doctor`
   → every line `ok` (state writable, `repo.git` present, `fetch origin main` ok, `gh auth status`
   ok, `gh` repo matches, `systemd-analyze` present, tz `Europe/Amsterdam`). A `fail` on `gh auth`
   here means `gh` needs a path under `$HOME` writable — the fix is a second `Environment=` in the
   drop-in (`GH_CONFIG_DIR` copy under the state dir), not a widening of `ProtectHome`.
5. `bash tests/acceptance/control_room_proposals.sh` (§ Hand-run acceptance) — all PASS.
6. `bash bin/verify.sh` green (drift clean: the drop-in compared, `bin/` deployed); commit and push
   by hand (auto-sync never pushes a clean tree).

## Hand-run acceptance (Dave, once, at land) and evidence-time

`tests/acceptance/control_room_proposals.sh [--screen http://100.86.82.16:8787]` runs on the box,
**creates no branch and no PR** — every positive case is a preview or a refusal, and the script greps
itself for `--submit`, `"stage":"submit"`, `gh pr` and `push` as a self-check before it starts. Steps,
each `PASS`/`FAIL`:

1. Installed: the drop-in is in `/etc`, `systemctl show control-room.service -p StateDirectory`
   answers `control-room-proposals`, `/var/lib/control-room-proposals/repo.git` exists, `doctor`
   (from a dave shell) is all `ok`.
2. Peer gate from this host: `curl` POST `preview schedule knowledge-digest` at the screen from the
   box → 403 `peer_denied`, and a new record under `/var/lib/control-room-proposals/proposals/`.
3. CLI previews (`python3 ~/agent-workforce/bin/workflow_pr.py … --preview` with the state root):
   `schedule knowledge-digest --on-calendar "Sun 07:00" --reason acceptance` → prints the diff (three
   files), the timezone block with CEST/UTC elapses, the catch-up sentence naming resume, and the
   checks (`manifest-joins` pass, `pinned-tests` names `tests/test_knowledge_digest_smoke.sh` if it
   pins the schedule, `drift-preview` lists `content differs: knowledge-digest.timer` as introduced);
   `schedule qmd-refresh --on-calendar "hourly"` → `not_calendar_timer`; `schedule buzz-agent@marcus`
   → `not_a_timer`; `retire knowledge-digest --reason acceptance-preview-only --receipts keep --notion keep
   --inbox keep --note "acceptance"` → the residue tables (branch: all non-blocking; box: the
   installed units, the deployed runner/profile/env example, the `dave-only` env line as
   `unverifiable`), the removal table, `deploy-preview` naming the deferred exclusions prune would
   also delete; `retire knowledge-digest` without `--note` → `retention_required`. `git ls-remote
   --heads origin 'control-room/*'` → empty (nothing was pushed).
4. Screen (from the Mac, printed instructions, no assertion): open
   `http://praetorium:8787/workflows/knowledge-digest` → Controls row 2 shows `Change schedule…` and
   `Retire…`; click **Change schedule…** → dialog prefilled `Sun 09:00` → set `Sun 07:00`, reason →
   **Preview** → the dialog shows the same diff and checks as step 3 → **Cancel**. No PR exists;
   `gh pr list --state open` on the Mac shows none from `control-room/`.

**Evidence-time (Dave's moment, not development-time):** the first real PR from the screen is
T5.4's decision — a retirement on the evidence a never-resumed workflow already has, or a schedule
change ahead of a resume. Its trace: the PR URL in the proposal record, the diff identical to the
preview, CI green (or draft with named reds), the land steps in the PR body executed by hand, and
for a retirement `bin/workflow_pr.py clear <id>` turning `tests/test_workflow_retirements.sh` green
again. Record it in the tracker row. No run is started for T5.3b.

## Seam deviations from T5.3 § Seams (each minimal, each stated)

1. **A `main()` binding in `bin/control_room_api.py`** beside the one seam edit site: the handler
   needs the worker bound per server (`server.RequestHandlerClass.proposals = …`), the same pattern
   T5.3a needs for `control`. Two lines, no shape change.
2. **One `<script>` line in `bin/control_room_view_workflow.py`**: the seam says T5.3b "moves" the
   proposal buttons off `actions.js`'s generic poster but provides no way to load `proposals.js`.
   Claiming the buttons in the capture phase avoids editing `actions.js` (T5.3a's extension target)
   at all.
3. **`stage: "list"`** added to `preview|submit`: a POST that reads, so the workflow page can show
   existing proposal PRs without a GET route the seam reserves to T5.3.
4. **Response fields** beyond the seam's `{stage, preview_token, diff, checks, residue}`: `proposal_id`,
   `base`, `branch`, `description`, `files`, `diff_sha256`, `submit_allowed`, `submit_blockers`,
   `retention`, `control`, and `pr.number`/`pr.draft` on submit. Additive.
5. **Extra HTTP statuses** 404 (unknown id — the stub already did this), 403 (`peer_denied`), 500
   (`failed`), 503 (`worker_unavailable`).
6. **Proposal records live under `/var/lib/control-room-proposals/proposals/`**, not under
   `~/agent-workforce/var/`: the screen cannot write `$HOME`, and the records belong with the clone
   they describe. `~/agent-workforce/var/control-proposals` is the loopback-dev default only.

## Out of scope / do not touch

- **T5.3 (sibling, owns):** `bin/control_room_{cadence,exceptions,benefit,lineage,static,views,view_exceptions,view_portfolio,view_benefit}.py`,
  `bin/control_room_serve.sh`, `bin/control_room_ui/{app.css,app.js,actions.js}`,
  `systemd/control-room.service` (this brief adds a drop-in **beside** it, never edits it),
  `design/benefit-ledger.toml`, `tests/test_control_room_{views,exceptions,benefit,cadence,lineage}.*`,
  `tests/control_room_fixture.py`, `tests/fixtures/control-room/**`. In `bin/control_room_api.py`
  only the proposals branch and the `main()` binding; in `bin/control_room_view_workflow.py` only the
  one `<script>` line.
- **T5.3a:** `bin/control_room_control.py`, `bin/control_broker.py`, `bin/control_broker_allowlist.py`,
  `systemd/control-room-broker.*`, `systemd/control-room.service.d/broker.conf`, `/var/lib/control-room/`,
  `/etc/control-room/`, `tests/test_control_broker.*`, `tests/test_control_room_control.*`,
  `tests/fixtures/control-broker/`, `tests/acceptance/control_room_controls.sh`, the `POST
  /api/v1/control/actions` branch, `bin/check_deploy_drift.sh` and `tests/test_deploy_drift.sh`
  (both siblings edit them; this brief edits neither — the drop-in is compared by the existing
  depth-2 drop-in scan).
- **T5.3c:** `bin/deliver.sh`, `bin/buzz_routes.env` (a retire PR drops a `bin/buzz_producers.tsv`
  row — a *producer* join the task row names — and never a `ROUTE_*` line), `bin/deliver_*.sh`, any
  Buzz route or incident-digest unit; `incidents()`/`usage()`/`activity()` semantics.
- **T5.3d:** `bin/control_room_handoffs.py`, `bin/control_room_ui/timeline.js`.
- **T5.2:** `bin/agent_propose.sh`, `bin/run_*_cc.sh` and every runner (a retire PR **deletes** a
  runner on a branch as the requested removal — it edits none), `bin/contract_exec.py`,
  `bin/workflow_receipt.py`, `profiles/` (same: deletion on a branch only, never an edit).
- **T5.4:** entries in `design/benefit-ledger.toml`; the retention decision is recorded here and
  acted on by Dave, never by the box.
- **W19's open questions**, unchanged: the `bin/` half of the drift check gets no exclusion
  mechanism (the residue report names it as "cleared only by `bin/deploy --prune`"), no expiry is
  added to `design/deploy-exclusions.toml`, `bin/deploy --prune` is never run by code here,
  `design/workflow-registry.md` is not edited (frozen, T6.4).
- Every workflow timer: no enable/disable/start/stop/restart; no `systemctl` in tests (shims only);
  the scanner sends read-only verbs only (asserted).
- `origin`: no test, smoke or CLI default reaches it; `push` exists only behind `BRANCH_RE` and only
  in `submit`. No `gh pr merge`, no `--force`, no `gh pr close`, no branch deletion on `origin`.
- `~/.config/**` (the `env_override` path is printed, never stat'ed), `~/.ssh`, `~/vault`,
  `~/agent-worktrees` — never read. `~/dev/agent-workforce` — never written except by `clear`
  (Dave's hand, one file).
- `.claude/briefs/current.md` — not written, not archived (orchestrator instruction).
- No manifest entry for the worker (an operator surface, T5.3's reasoning); no
  `config/fleet-units.tsv` change beyond what a retire PR itself proposes on its branch.

## Notes / preconditions

- **Complete option taken** (no MVP): both kinds, two-stage preview/submit with byte-identical diff,
  the full check bundle with introduced-drift diffing and prune-side-effect listing, the W19-class
  scanner in both directions with the registry consumer, the dialog UI, CLI parity, `doctor`,
  acceptance script — one land.
- **In-process worker with a `StateDirectory`, not a broker or a transient unit**: the gh token is
  readable by every dave process today, so a root or socket boundary would protect nothing; the
  properties that matter (branch namespace, no merge, no live-tree write) are code-and-test
  properties, and a synchronous stage is 10-20 s measured. `ProtectHome=read-only` stays; the
  drop-in pattern is T5.3a's and both drop-ins coexist.
- **Bare clone of `origin` rather than a worktree of `~/dev/agent-workforce`**: worktrees write into
  the canonical checkout's `.git/worktrees/` (under `$HOME`, unwritable from the screen), and the PR
  must be against GitHub's `main`, not the box's possibly-ahead one. Cost: one 21 MB clone and a
  fetch per stage.
- **Preview identity = diff bytes, not base sha**: an unrelated commit on `main` between preview and
  submit must not force a re-preview (the auto-sync timer commits every 15 min), while any change
  to the previewed bytes must. TTL 30 min because a diff is read, not glanced at.
- **The generator never edits a test**: a pinned literal is a claim the gate makes on purpose
  (`::control-room-30-of-31`, `OnCalendar=Mon 09:07`); rewriting it silently would defeat the
  claim. The one exception is T5.3's explicit hand-off of the 30/31 counts, done only when they are
  named constants; otherwise the acknowledge-and-draft path keeps the red visible in CI and names
  the fix in the PR body.
- **Retirement archives units and contracts rather than deleting them**: `tests/test_workflow_coverage.py`'s
  orphan rule keys on `systemd/archive/` ("the act that retires its script"), and a retired
  contract is T5.4's evidence. Runners, profiles and suites are deleted: nothing joins against them
  once the unit is archived, and a deployed copy is exactly the W19 residue the scanner exists to
  name.
- **`bin/` residue is cleared only by `bin/deploy --prune`**, and the PR says what else prune deletes
  (measured from `--dry-run --prune` at preview) — W19's "not a side effect to hide in a docs PR",
  made a section.
- **The deny-listed override is Dave's attestation, not a measurement**: W19 said "there is no
  instrument here; the only one is a human running `ls`". The scanner prints the path and the
  commands; `clear --env-removed` records that he did. The fixture proves the scanner never stats it.
- **`tests/test_workflow_retirements.sh` is red between merge and cleanup by design** — the same
  window the drift check is already red for, now with names and the command that ends it. With zero
  entries (this land) it is green everywhere; its box half adds one `ci-expected-skips.txt` line.
- **`stage: "list"` is a POST** because the seam reserves GET routes to T5.3; the records carry no
  secret and no diff in list form.
- **Two-trigger workflows**: a schedule change is per timer (`trigger` required, as T5.3a's
  `run_now`); a retirement is per logical workflow (both units, one record) because the product is
  one.
- **Timezone is the box's** unless the spec names one: `OnCalendar` is evaluated by systemd in the
  unit's zone, DST-shifting for `Europe/Amsterdam`; the PR shows both local and UTC for that reason,
  and the reader learns which the fleet's other timers assume.
- **Collision window is a warning**: `agent_propose.sh`'s global flock makes a collision a silent
  `SKIP` (agent-model §6.6), which is worth a sentence in every schedule PR and never a refusal.
- **`gh` author**: PRs are opened by `Dave1524` (the only login on the box); commits are authored
  `Praetorium Control Room` so `git log` distinguishes a screen-made commit from Marcus's; the
  request line in the body names the actor and peer address.
- Python 3.11+ stdlib only (`tomllib`, `zoneinfo` in the shim); `git` and `gh` are the only tools,
  both present on the box and on the CI runner (gh via the shim in tests). No new dependency.
- **Depends on T5.3 landing first** (seam files); T5.3a may land before or after (disjoint sites;
  a textual conflict in `control_room_api.py`'s import block or `main()` is resolvable by keeping
  both lines).
