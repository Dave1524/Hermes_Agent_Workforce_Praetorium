# Brief: Detect deploy drift in every tree that can lose a unit
**Date:** 2026-09-01   **Verify:** `bash bin/verify.sh` from the repo root (syntax + shellcheck -S error over `bin/`, then every `tests/*.sh`)

This is Phase-B brief 2: D8's source-vs-deployed drift assertion, widened. Read
`design/open-decisions.md` D8 (line 673) and § Phase-B brief order item 2 (line 886) before
starting. This brief does not restate D8's measurements — it states what to build, and it
corrects D8 in one place that changes the design: **D8 names three unit trees and there are
four.**

**It ships red.** A drift check that is green the moment it lands has not been shown to detect
anything. What is red on arrival is named in criterion 11 and is not negotiable away by
exclusion: the reds are fixed by giving the units a source, not by declaring them uninteresting.

## Acceptance criteria

1. **One script owns the comparison.** `bin/check_deploy_drift.sh` is the single answer to "is
   the box running what this repo says". A second, narrower owner already exists —
   `check_deploy_drift()` at `bin/fleet_eval_behaviour.py:95`, which compares exactly one file
   (`bin/buzz_routes.env`) and reports it as `route-table-deployed`. Either it delegates to the
   new script or it is recorded, in its own docstring, as the deliberately narrower case that
   runs inside the fleet-eval report. Two functions with the same name answering the same
   question differently is the drift this brief exists to catch.

2. **Four trees are compared, each named in the script, with the meaningful comparison stated
   for each.** There are FOUR unit trees, not three. D8 names source `systemd/`, the staging
   copy `~/agent-workforce/systemd/`, and live `/etc/systemd/system/`. It never mentions
   `~/.config/systemd/user/`, which holds **nine** unit files with zero source counterpart in
   this repo — measured 2026-09-01, re-measured for this brief: `buzz-agent@.service`,
   `buzz-notion-broker.service`, `buzz-pr-watch.{service,timer}`, `hermes-gateway.service`,
   `nekovri-subsidy-kickoff.{service,timer}`, `nekovri-subsidy-watchdog.{service,timer}`.
   The comparisons that mean something:
   - `bin/` ↔ `~/agent-workforce/bin/` — the runtime tree is what every unit's `ExecStart`
     names (21 of 26 source services; e.g. `systemd/agent-proposal.service:20`).
   - `systemd/*.{service,timer}` and `systemd/*.d/*.conf` ↔ `/etc/systemd/system/` — **directly.**
   - `~/.config/systemd/user/` ↔ its source home in this repo, which does not exist yet
     (criterion 6).
   - the staging copy `~/agent-workforce/systemd/` is **inert** — systemd reads `/etc`, never it
     (proof: `content-inbox-finalize.{service,timer}` sit in the staging tree today and
     `systemctl list-unit-files` does not know them). The script must state in one line why it
     is not a side of any comparison, so the next reader does not add it back.

3. **`bin/deploy` never writes `/etc`** — verified 2026-09-01 by grep over `bin/deploy`, which
   returns no match for `/etc` at all; its `PATHS` array (`bin/deploy:20`) is
   `bin profiles docs CLAUDE.md AGENTS.md README.md config systemd`, all rsynced into
   `$DEST=~/agent-workforce`. So comparing source against the **staging** copy goes green the
   moment a unit is deployed while `/etc` stays stale — a false green in precisely the direction
   that matters. Measured today, staging is byte-identical to source for all 53 units, so that
   false green is live and available right now. `CLAUDE.md:75` ("deployed runtime copy … that
   systemd actually execs") is true of `bin/` and false of `systemd/`; do not take it as licence.

4. **Membership is compared in BOTH directions, not only content.** A unit present in one tree
   and absent from the other is invisible to a byte-comparison of the units that exist in both,
   which is all that `e0e4b25` and the 2026-09-01 deploy checked. Both directions are red
   conditions: `/etc`-only (a rebuild from source loses it) and source-only (the box is not
   running what the repo says it runs).

5. **Ownership fails closed: an `/etc` unit matching neither source nor a declared exclusion is
   RED.** The filter is needed because a bare set-difference returns OS units — today, with the
   comparison restricted to regular files matching `*.service`/`*.timer`, the noise is exactly
   `ollama.service`; the 8 OS symlinks (`chronyd`, `iscsi`, `syslog`, `vmtoolsd`, four
   `dbus-org.freedesktop.*`) and 6 `*.bak*` files drop out on that restriction alone.
   **Ownership must be decided by a declaration in this repo, never by a heuristic over unit
   contents.** The obvious heuristic — "references `/home/dave`" or "`User=dave`" — misclassifies
   one of our own units: `systemd/ttm-pool-drain.service` has neither (it runs as root,
   `ExecStart=/usr/local/bin/ttm-pool-drain`). And "unknown ⇒ ignore" is the defect class this
   repo keeps rediscovering: a check that asks a list whether it is fine cannot fail.

6. **The two exclusion lists are distinct and the dated one expires.** Permanent third-party
   (`ollama.service` and the OS symlinks) is a reviewed, stable list. Ephemeral-on-purpose is a
   **dated** declaration, and an entry whose date has passed is itself a failure — otherwise the
   list teaches everyone to ignore a red. **The dated list already has a home:** the manifests
   carry `status = "campaign"` plus `expires` (`design/agent-model.md:126-127`), and the two
   campaign families are already declared correctly —
   `design/agents/augustus.toml:103` (`expires = "2026-09-03 23:00"`) and `:117`
   (`expires = "2026-09-04 01:30"`). Read that, do not re-key it into the script. Any unit with
   no `[[workflows]]` entry at all needs one before it can be excluded.

7. **The nine user-tree units get a source home in this repo, and three drop-ins never can.**
   `buzz-agent@.service` is in that unsourced tree **and was edited on 2026-09-01 by brief 1** to
   add `Environment="CLAUDE_CODE_EXECUTABLE=…"` (`~/.config/systemd/user/buzz-agent@.service:41`).
   The fleet's core unit has no source of truth and would be invisible to the check exactly as D8
   specs it — while `tests/test_fleet_guards.sh:81,89` already asserts that line, so a rebuild
   that loses the unit turns brief 1's guard red with nothing in this repo to restore from.
   The user tree also holds 11 drop-in `*.conf` files across 6 `*.d` directories, and **three of
   them carry `BUZZ_AUTH_TAG`** — `buzz-agent@augustus.service.d/auth.conf`,
   `buzz-agent@trajan.service.d/auth.conf`, `nekovri-subsidy-watchdog.service.d/auth.conf`.
   Those are credentials. They must **never** enter this repo, and their exclusion is a declared,
   permanent entry with that reason — not a silent skip and not a `.gitignore`.

8. **The source home for user units cannot be mistaken for a system unit by anything.**
   `systemd/` holds 53 units today, all system-scope, and the user tree is not a subset of it.
   (The queue's `must_carry` says 47, measured before `d72f562` added the six
   `praetorium-phaseb-brief@*` units; 47 + 6 = 53, and the "all system-scope" half is unchanged.)
   Whatever home is chosen must not make the drift check demand that a user unit appear in
   `/etc`, must not make `docs/runbook.md:250` ("Install units from `systemd/`") install a user
   unit system-wide, and must not be swept up by `systemd/archive/`'s meaning (six retired units
   live there; `content-inbox-finalize.{service,timer}` were moved there by an `Auto-sync:`
   commit, `98966eb`).

9. **Three callers, and the timer is not optional.** `bin/verify.sh` as a hard fail;
   `bin/deploy` as a post-condition (a deploy that did not converge is a failed deploy, not a
   quiet one); a daily timer for the `/etc`-hand-edit case. The timer is mandatory because a
   commit-time gate cannot see that class at all — and because `bin/auto-sync` commits and pushes
   with `git add -A` every 15 minutes without ever calling `verify.sh`
   (`bin/auto-sync:32-34`), so "the gate runs when a human commits" is not true on this box.

10. **The check reports; it never converges.** No writes to `/etc` (root-owned; `dave` cannot
    write it without sudo), no `bin/deploy` invocation, no `systemctl`, no `daemon-reload`, no
    deletion of anything in any tree. Its exit code and its output are the whole product.

11. **On arrival it is RED, and the red is named:** the nine unsourced user units above, plus
    `fleet-turn-check.{service,timer}` if precondition 1 has not been done first (still `/etc`-only
    at 2026-09-01 19:45). Everything else measured clean today: zero content drift in `bin/`
    (the only runtime-only files are seven `*.bak-*`, which the ignore rule covers), zero content
    drift across all 53 units against `/etc`, and `systemd/qmd-mcp.service.d/gpu.conf` identical
    to its `/etc` copy. **Done means those reds are FIXED — the units have a source — not
    excluded.** The `verify.sh` hard-fail wiring is turned on only once the gate is honestly
    green; landing a hard fail over a red the brief chose not to fix blocks briefs 3-6 behind a
    known-red gate, and softening the check to get green is out of scope by rule.

12. **The new timer is registered everywhere units are registered**, or it is the next thing that
    goes missing: a `[[workflows]]` entry with `unit`, `status`, `suite`, `alerted`, `in_repo`
    (`design/agent-model.md:118-131`), a row in `docs/runbook.md` § Job wiring, and a name that
    the reporting jobs' globs actually match — `'overnight-*' 'agent-*' 'augustus-*' 'bd-*'
    'weekly-*'` at `bin/local_tier_eval.sh:51` and `bin/overnight_pre_snapshot.sh:81-82`, plus the
    explicit list at `bin/praetorium-status.sh:17-20`. A name outside those globs is invisible to
    every report on this box. Do **not** fix the glob defect here; it is W3, brief 6.

13. **Two stale claims are corrected in the same change**, because both describe exactly what
    this check measures: `design/agent-model.md:403` § 6.7 says four unit families exist only in
    `/etc` and names `ttm-pool-drain` — which the same file already contradicts at line 167
    ("`in_repo = true` since D2 adopted its unit"). Measured today it is three families / six
    files: `fleet-turn-check` and the two campaigns. And
    `systemd/praetorium-phaseb-brief@.service:4-6` still calls those units "/etc-only
    scaffolding" after `d72f562` gave them source copies.

14. `bash bin/verify.sh` exits 0.

## Files to create

- **`bin/check_deploy_drift.sh`** — the comparison, once. Exits non-zero on any differing,
  missing, or unexplained file in any of the compared trees; prints one line per finding naming
  the tree, the direction and the file. Ignores `__pycache__/` and `*.bak*` (both are live in the
  runtime tree today: `~/agent-workforce/bin/__pycache__` and seven `*.bak-*` scripts).
  It must accept root overrides from the environment for every tree it compares — the test suite
  builds synthetic trees and cannot be allowed to depend on the box's live state (see Test plan).

- **`tests/test_deploy_drift.sh`** — the suite. See Test plan.

- **The source home for the nine user units** (expected: `systemd/user/`), holding the unit files
  only. Not the credential-bearing drop-ins.

- **A permanent ownership declaration** for units that are on this box legitimately and will never
  have a source here — `ollama.service`, the OS symlinks, and the three `auth.conf` drop-ins with
  their reason. Keep it as small as `design/fleet-suites.toml` is: it exists to answer "is this
  ours" and "may this ever be committed", not to become a second registry. The *dated* half is
  not in it — that lives in the manifests (criterion 6).

- **`systemd/<drift-check>.{service,timer}`** — daily. `Type=oneshot`, `User=dave`,
  `OnFailure=agent-alert@%n.service`, `ExecStart` pointing at the **runtime** copy
  (`/home/dave/agent-workforce/bin/…`), matching every other job here. Note the consequence: the
  timer runs the *deployed* checker, so an undeployed checker fails its own unit — that is
  correct behaviour and the alert is the signal.

## Files to modify

- **`bin/verify.sh`** — add the drift check as a hard fail, after the shellcheck block and before
  or alongside the `tests/*.sh` loop. Gate it on the reds being cleared (criterion 11).

- **`bin/deploy`** — call the check as a post-condition after the rsync loop (`bin/deploy:71-82`),
  in the non-`--dry-run` path only. Do not make it change what deploy *does*: `--prune` behaviour
  stays exactly as it is.

- **`bin/backup_config.sh`** — `bin/backup_config.sh:14-20` enumerates unit names from this repo's
  `systemd/` glob and includes each one **that is installed under `/etc`**. Two consequences that
  make the adoption in criterion 7 cosmetic if left alone: a unit with no source is not backed up
  at all, and a user unit is never under `/etc` so it can never match. Extend the enumeration to
  the new source home and the user tree. **Never** add the three `auth.conf` drop-ins — the
  inventory at `docs/runbook.md:224` already distinguishes assets that are never backed up, and
  credentials are that class.

- **`docs/runbook.md`** — a Job wiring row for the new timer (§ Job wiring, line 14); the backup
  inventory row at line 224 (it currently describes system units only); and rebuild checklist
  step 5 at lines 249-251, which says "Install units from `systemd/`" and is the exact procedure
  that silently loses every unit this brief is about.

- **`design/agents/trajan.toml`** — a `[[workflows]]` entry for the new drift timer (platform
  job, `suite = ["tests/test_deploy_drift.sh"]`). The five user-tree units that are trajan's
  or the fleet's, and the `praetorium-phaseb-brief@*` scaffolding, need entries too if they are
  to be excludable or assertable at all; `fleet-turn-check` shows the shape at lines 48-56
  (`in_repo = false`, `suite_exempt`), and `buzz-pr-watch` at lines 184-192 shows a user-scope
  entry already in the schema.

- **`design/agent-model.md`** — § 6.7 (line 403) per criterion 13, and the schema block at
  118-131 if the ownership declaration adds a field.

- **`design/open-decisions.md`** D8 (line 673) — record the fourth tree, the corrected counts, and
  that `in_repo`/`expires` are the declaration surface. D8's own "Method note" is the lesson being
  applied: a cleared baseline is only cleared for the property you compared.

- **`systemd/praetorium-phaseb-brief@.service:4-6`** — the stale `/etc`-only comment.

## Test plan

One file, `tests/test_deploy_drift.sh`, following `tests/test_fleet_guards.sh` and
`tests/test_phaseb_brief_jobs.sh` verbatim: `set -uo pipefail`, the `assert()` helper that scopes
`pipefail` **off** inside the condition (`tests/test_fleet_guards.sh:38-45`), and `yes | grep -q y`
as the first assertion. That canary is not decoration — under `pipefail` a condition ending in
`grep -q` fails a true assertion and silently passes a negated one, which is how this gate
certified nothing for a while in August.

**The suite tests the checker against fixtures; it does not test the box.** Build synthetic trees
under `$TMPDIR` (`bin/verify.sh` already owns one temp root and exports `TMPDIR`) and point the
script at them. This is the difference between a test and a status report: a suite that asserted
"the live box is clean" would be red for reasons that have nothing to do with the code under test,
and every future implementer would learn to ignore it.

What must fail before the change exists, and how — one assertion per drift class, each proven by
constructing it:

1. **content differs** — same filename, different bytes, in `bin/` and again in a unit tree.
2. **source-only** — a unit in the source fixture and not in the `/etc` fixture.
3. **etc-only, ours** — the class `e0e4b25` and the 09-01 deploy could not see. This is the one
   that loses `fleet-turn-check`.
4. **etc-only, third-party** — present in the permanent declaration ⇒ silent.
5. **etc-only, undeclared** — RED, not silent. Fails closed.
6. **dated exclusion, live** ⇒ silent; **dated exclusion, expired** ⇒ RED. Drive it from a
   fixture clock, not from `date`, or the assertion is correct only until the date passes.
7. **user-tree unit with no source** ⇒ RED; **credential drop-in** ⇒ declared, excluded, and
   asserted absent from `git ls-files`.
8. **drop-in `*.d/*.conf` differs** ⇒ RED. A drop-in silently overrides its unit; today
   `qmd-mcp.service.d/gpu.conf` is the only one on the system side and it is clean.
9. **ignored classes stay ignored** — `__pycache__/`, `*.bak*`.
10. **the three callers are wired** — `bin/verify.sh` and `bin/deploy` name the script;
    the timer unit exists in `systemd/`, its `ExecStart` resolves to a file that exists in the
    runtime tree, and its `[[workflows]]` entry exists with a `suite` naming this file.

**The constraint that governs the whole suite: a drift class is proven by constructing it in a
fixture, never by damaging the live box.** Do not remove a unit from `/etc`, do not edit a live
unit, do not stop a timer, and do not `git rm` a source unit "to watch it go red". The live
verdict is what the `verify.sh` and `deploy` callers produce on a real run — reported, not
manufactured.

**Live verification, separate from the suite:** run `bash bin/check_deploy_drift.sh` by hand and
read its output against the list in criterion 11. Before believing any clean result, assert the
globs matched a non-empty set — D1's first measurement globbed a path that did not exist and
returned a clean `0` for every connector.

## Out of scope / do not touch

- **Writing `/etc`.** Installing the new timer is `sudo cp` + `daemon-reload`, and `/etc/systemd/system`
  is root-owned — that is Dave's action, exactly as `systemd/ttm-pool-drain.service:1-4` records for
  its own unit. State it as a handoff step; do not attempt it, and do not add sudo to any script here.
- **Deleting the campaign units.** `praetorium-content-strategy-research.*` and
  `praetorium-faceless-content-research.*` are still firing — last slots 2026-09-03 23:00 and
  2026-09-04 01:30, both confirmed scheduled in `list-timers` at 2026-09-01 19:40. They get a
  dated exclusion here and are deleted by brief 6, after their last firing. Deleting early
  destroys a campaign mid-flight.
- **The `praetorium-phaseb-brief@*` units.** The queue entry warns they are ephemeral `/etc`-only
  scaffolding that must land on the dated exclusion list or be deleted, or the check goes red
  naming its own scaffolding. **Measured correction: they are no longer `/etc`-only** — `d72f562`
  committed all six to `systemd/`, and source and `/etc` are byte-identical today. The trap simply
  moved: on the day they are deleted from `/etc` they become *source-only*, which is red in the
  other direction. Give them a dated declaration now; do not delete them in this brief, and do not
  delete their source copies either — brief 6 owns the cleanup and this is the run writing them.
- **`bin/deploy --prune`.** The staging tree holds three orphans today —
  `content-inbox-finalize.{service,timer}` (archived from source by `98966eb`) and
  `discord-bot.service` — because deploy is additive. Running `--prune` would remove them and
  much else; it is a live-tree deletion, so it is Dave's call and a separate change. Name the
  orphans in the brief's output; do not prune.
- **W3's `praetorium-*` glob defect** (six files, best coverage 9 of 19) — brief 6.
- **`bin/fleet_eval_behaviour.py`'s report format.** Criterion 1 is about ownership of the
  comparison, not about restructuring the fleet-eval scorecard.
- **Anything the fleet guard suite asserts** — `~/.claude/settings.json`, the strict settings
  file, the vault hooks. Brief 1 landed those; this brief only *adds* a source copy for the unit
  that carries `CLAUDE_CODE_EXECUTABLE`.
- **Weakening any check to get green.** Not the drift check, not `verify.sh`, not an exclusion
  used as a substitute for giving a unit a source. If a red cannot be fixed, it stays red and is
  reported.

## Notes / preconditions

**Preconditions — both are repo-side and unblocked; neither is a human action.**

1. **Backport `fleet-turn-check.{service,timer}` into `systemd/` from `/etc` BEFORE the check
   lands.** Still `/etc`-only, re-confirmed 2026-09-01 19:45. Its `ExecStart` is
   `/home/dave/.config/buzz-team/fleet-turn-check.sh`, which is **not** in this repo and is not
   being adopted — `design/agents/trajan.toml:52` already declares that as `suite_exempt`. Copy
   the unit only, byte-for-byte, and flip `in_repo` in the manifest in the same change.
2. **Exclude `praetorium-content-strategy-research.*` and `praetorium-faceless-content-research.*`
   with a dated entry** (criterion 6). Their `expires` values are already correct in
   `design/agents/augustus.toml:103,117`.

**Measured on the box, 2026-09-01 19:30-19:45** (re-measure anything you intend to rely on; that
is the whole point of this brief):

- `systemd/`: 53 top-level unit files (26 `.service`, 27 `.timer`), all system-scope, plus
  `systemd/archive/` (6 retired units) and `systemd/qmd-mcp.service.d/gpu.conf`.
- `/etc/systemd/system/`: 60 regular `*.service`/`*.timer` files, 8 OS symlinks, 6 `*.bak*` files,
  and two drop-in dirs (`qmd-mcp.service.d`, `ollama.service.d`).
- **Zero content drift** today: every one of the 53 source units is byte-identical to its `/etc`
  copy, and `bin/` is identical to `~/agent-workforce/bin/` for every non-`*.bak*` file.
- `/etc`-only and ours: `fleet-turn-check.{service,timer}` + the four campaign files.
  `/etc`-only and not ours: `ollama.service`.
- `~/.config/systemd/user/`: the nine units of criterion 2, 11 drop-in `*.conf` files in 6 `*.d`
  dirs, 3 of them carrying `BUZZ_AUTH_TAG`. `buzz-agent@.service` mtime 2026-09-01 18:51 (brief 1).
  `nekovri-subsidy-{kickoff,watchdog}.timer` are `disabled`/`inactive` — spent scaffolding in the
  user tree, the same shape as the `/etc` campaigns.
- `~/agent-workforce/systemd/`: 56 unit files = the 53 plus three orphans.

**Ordering trap, and it will bite whoever lands this.** With drift wired as a hard fail in
`verify.sh`, the normal loop (edit source → verify → commit → deploy) inverts: verify is red until
`bin/deploy` runs, and `bin/deploy:52-55` warns when the source tree is dirty. Neither blocks, but
the order becomes edit → deploy → verify → commit, and that must be written down in
`docs/runbook.md` or every future session hits a red it cannot explain. Note also
`bin/deploy:45-47` refuses to deploy onto a git tree, so the source tree can never be its own
destination.

**`agent-workforce-auto-sync.timer` fires every 15 minutes** and commits any dirty tree with
`git add -A` under a generic `Auto-sync:` message (`bin/auto-sync:32-34`) — it is how
`content-inbox-finalize` was archived without a word of explanation in `98966eb`. Commit each
coherent piece immediately, or the message describing *why* is lost. For a long batch, stop the
timer first and restart it after.

**Why existence drift is the expensive class, in one chain:** no source ⇒
`bin/backup_config.sh:17` cannot enumerate it ⇒ it is in no tarball ⇒ `docs/runbook.md:249-251`
rebuilds `/etc` from the tarball and `systemd/` ⇒ the unit is gone, and nothing anywhere reports
its absence. That chain currently runs through the entire Buzz fleet, including the unit brief 1
edited yesterday.
