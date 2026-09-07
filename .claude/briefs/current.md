# Brief: Content run — corpus acquisition across the bwrap seam, and a sentinel table that cannot fall through
**Date:** 2026-09-07   **Verify:** `bash bin/verify.sh` from repo root
**Deploy ordering:** edit → `bin/deploy` → `bash bin/verify.sh` → commit. `bin/check_deploy_drift.sh`
is inside the gate, so the gate is RED until `bin/deploy` runs. This is expected, not a bug.

## Problem (measured 2026-09-07, do not re-derive)

Three defects, one incident. `augustus-content.service` failed 2026-09-07 01:51:59 after burning
its full 20-minute wait.

1. **Augustus can never fetch the site repo.** He is the only agent on codex-acp; his bwrap
   namespace carries `--tmpfs /home/dave/.ssh`. The site remote is `git@github-website:` — an
   ssh-config *alias*. With an empty `~/.ssh`, `ssh` cannot resolve it:
   `Could not resolve hostname github-website: Temporary failure in name resolution`.
   Reproduced deterministically with `GIT_SSH_COMMAND="ssh -F /dev/null"`. Nine consecutive
   nights (08-14 → 09-06) augustus reported "origin unreachable" while the host-side
   `content_state.sh` receipt seconds later reported `corpus: fetched`. It is not transient and
   never once succeeded. `_read_blog_ts()` still works in his namespace (the ref is on local
   disk); **only `_fetch()` fails**.
2. **`RUN-FAILED:` is an unrecognised sentinel.** `bin/run_content_via_buzz.sh` matches only
   `SKILL-READ-FAILED:` and `DECLINE:`. Augustus replied `RUN-FAILED: ...` at 01:33:25 — 110s
   after dispatch. Nothing matched, the poll ran to its deadline, and the run logged
   `no board movement and no reply within 1200s`, asserting the opposite of what happened. This
   is verbatim the defect the script's own comment says was fixed once for `SKILL-READ-FAILED`;
   it was fixed as a special case, so the next sentinel reintroduced it.
3. **The profile never defines the corpus-refusal outcome**, so augustus improvised three
   behaviours over nine nights: `DECLINE:` (08-14/15), draft-anyway-with-a-caveat (09-02 → 09-05,
   10 posts shipped with the gate not running), `RUN-FAILED:` (09-06).

Site `origin/main` is `1785209`, 2026-08-11T07:47:52Z, 644.5h old — real, but a separate content
decision and **not** the cause. Publishing to the site would drop the age under 72h, silence the
refusal, and leave the gate permanently blind for augustus (`_freshness_line` prints
`OFFLINE — last known ref` and **exits 0**). That is failing open; do not treat it as a fix.

## Acceptance criteria

- Augustus's `published_corpus.py list` / `check` succeed inside his namespace with no
  credential, no ssh config, and no network reachable from that namespace.
- No credential, key, or ssh config is made readable inside the bwrap namespace. The corpus is
  public data; this is a transport split, mirroring `buzz-notion-broker.py`. Widening the
  namespace is explicitly out of bounds (`~/CLAUDE.md`).
- Corpus provenance is always visible in output: whether it came from a live fetch, a
  host-captured snapshot, or a local ref that could not be refreshed. No silent fallback.
- A corpus that cannot be acquired **on the host** stops the run before dispatch, rather than
  producing an ungated draft.
- Any terminal reply from augustus ends the wait promptly and is reported verbatim. The run never
  logs "no reply" when a reply exists.
- A sentinel the profile emits but the dispatcher does not know fails the verify gate, rather than
  costing a 20-minute stall in production.
- Existing outcomes are unchanged: board moved → 0; `DECLINE:` → 0 with `decline_event=` recorded;
  `SKILL-READ-FAILED:` → 1; genuine silence → 1; trigger never published → 4.

## Files to modify

- **`bin/published_corpus.py`** — split acquisition from interrogation.
  - Add `VP_CORPUS_SNAPSHOT` (default `~/agent-workforce/var/published_corpus.json`) and
    `VP_CORPUS_SNAPSHOT_MAX_AGE_HOURS` (default `24`).
  - New `snapshot` subcommand: acquire via git, write `{captured_at, freshness, articles}`
    atomically (temp file + `os.replace`). Exit non-zero if the fetch failed or the existing
    refusal condition holds — this is the host's own honesty check.
  - `load_corpus()` resolution order: live fetch → host snapshot (if captured within
    `SNAPSHOT_MAX_AGE_HOURS`) → local ref (only while `ref_age_hours <= MAX_LAG_HOURS`) → refuse.
    The refusal message must now also say whether a snapshot was absent or too old.
  - `freshness` dict gains `source` (`origin` | `snapshot` | `local-ref`) and, for snapshots,
    `captured_at` + `snapshot_age_hours`. Keep `fetched` and `ref_age_hours` — `content_state.sh`
    reads both and must not break.
  - `_freshness_line()` names the source, so the header augustus reads states provenance.
- **`bin/run_content_via_buzz.sh`**
  - After the board baseline and **before** dispatch, capture the corpus snapshot; on failure
    `crash` (exit 4) with a message saying the run was not dispatched because the gate could not
    be armed. Same precedent and rationale as the existing "board that will not read is a crash".
    Resolve the binary through a `CONTENT_CORPUS_BIN` seam, as `DIGEST_BIN`/`DELIVER_BIN` are.
  - Replace the two hardcoded sentinel branches with **one ordered table** driving the existing
    single `sentinel_reply()` reader: `DECLINE:`→0 (records `decline_event=`),
    `SKILL-READ-FAILED:`→1 (keeps its current three explanatory log lines),
    `RUN-FAILED:`→1 (new). Adding a sentinel must be one table row plus its message.
  - At the deadline, before claiming silence, re-read for **any** augustus reply since dispatch.
    If one exists, log it verbatim with its event id and exit 1 saying no sentinel matched and
    that the table needs the new sentinel. Only genuine silence keeps the existing
    "no board movement and no reply" line. Do **not** add a regex catch-all inside the poll loop —
    a `STATUS:`-shaped progress line would kill a live mid-work run.
  - In `sentinel_reply()`'s embedded python, skip blank lines so an empty prefix cannot match one.
- **`profiles/augustus_content_task.md`** — STEP 1, immediately after the `published_corpus.py list`
  command: define the single outcome for a non-zero exit. Do not draft, do not pitch, do not reply
  `DECLINE:`; reply exactly `RUN-FAILED: published_corpus <stderr message>` and stop. State that
  the corpus may legitimately arrive from a host-captured snapshot and that the `# corpus from …`
  header line is to be reported, not ignored. Mirror the wording style of the existing
  `SKILL-READ-FAILED:` paragraph — that is the house pattern for this class.

## Files to create

None. Both test files already exist and are extended in place.

## Test plan

**`tests/test_published_corpus.py`** (plain `check(label, cond)` style, offline, no git/network —
stub `corpus._fetch` and `corpus._ref_age_hours` / `corpus._read_blog_ts` against the existing
`FIXTURE`):
- fetch fails + snapshot captured within max age → corpus loads, `freshness["source"] == "snapshot"`,
  no refusal. *This is the augustus case and is the regression under test.*
- fetch fails + snapshot older than max age + ref age > `MAX_LAG_HOURS` → refuses, and the message
  names the snapshot as stale.
- fetch fails + no snapshot + ref age > `MAX_LAG_HOURS` → refuses (unchanged behaviour).
- fetch fails + no snapshot + ref age <= `MAX_LAG_HOURS` → loads, `source == "local-ref"`.
- fetch succeeds → `source == "origin"`, and `fetched` / `ref_age_hours` keys still present for
  `content_state.sh`.
- `snapshot` writes a file containing `captured_at` and the parsed articles, and exits non-zero
  when the fetch failed.
- `_freshness_line()` output names the source in every one of the three modes.

**`tests/test_run_content_via_buzz.sh`** (extend; reuse `reset_case` / `event` / `run_dispatch`,
and keep the `yes | grep -q y` pipefail canary):
- `RUN-FAILED: ...` reply exits 1, does **not** log `no board movement and no reply`, is not
  reported as a decline, and quotes the reason. Assert the log line, not just the exit code — the
  existing `SKILL-READ-FAILED` comment records why an exit code alone passed while the branch was
  dead.
- An unknown sentinel (e.g. `WAT-FAILED: something`) exits 1, logs that no sentinel matched, quotes
  the line and event id, and does **not** log `no board movement and no reply`.
- Genuine silence still logs `no board movement and no reply` and exits 1.
- **Bidirectional pin:** every `^[A-Z][A-Z0-9-]*:` sentinel literal instructed in
  `profiles/augustus_content_task.md` appears in the runner's table, and vice versa. This is the
  assertion that makes the whole class die once instead of per-sentinel.
- The runner captures the corpus snapshot before dispatch; a failing capture exits 4 and **no
  send reaches the stub** (assert `$STUB_ARGV` carries no `messages send`).
- Unchanged outcomes still hold: board moved → 0, `DECLINE:` → 0 with `decline_event=` written,
  wrong-pubkey and pre-dispatch-epoch replies still ignored.

## Out of scope / do not touch

- **Do not widen the bwrap namespace** or hand any credential, key, or ssh config into it.
- Do not publish to the website, or change `VP_CORPUS_MAX_LAG_HOURS` (72) to mask the 644h age.
  The staleness is Dave's content decision and is tracked separately.
- Do not touch `bin/content_state.sh`, `bin/content_moved.sh`, `bin/deliver_content.sh`,
  `bin/deliver_dispatch.sh`, `bin/brief_collision_check.py`, or the Notion broker.
- Do not change the `4` / `1` / `0` exit contract, the route table, the kind (45001), or
  `bin/deliver.sh`'s sole ownership of `buzz messages send`.
- No changes to `profiles/standing_research_cc_task.md` or `profiles/archive/claudius_task.md`,
  which also call `published_corpus.py` — they run on the host and are unaffected.
- Not in this brief: capturing the "special-case fall-through" learning (offered separately).

## Notes / preconditions (confirmed this session)

- bwrap config read in full from `/proc/<bwrap-pid>/cmdline` (21 args, all accounted for):
  `--dev-bind / /`, `--tmpfs` over exactly `~/.ssh`, `~/.config/buzz-agents`,
  `~/.config/agent-workforce`, `~/.codex`, and a `--ro-bind` of a `denied` placeholder over
  `ENCRYPTION_RECOVERY.md` and `.confidential.img`. Two consequences, both confirmed:
  `~/agent-workforce/var/` is under the dev-bind and covered by no tmpfs, so a host-written
  snapshot there is **readable inside the namespace with no namespace change**; and there is
  **no `--unshare-net`**, so the namespace has working network — the fetch fails purely for the
  missing ssh alias config, which rules out "give the sandbox network" as a fix.
- `bin/deploy` PATHS includes `bin` and `profiles`, so both changed trees deploy. Drift is
  checked for `bin/` only; profiles deploy without a drift assertion.
- Harness split confirmed live: marcus/claudius/trajan/aurelian on `node` (claude-agent-acp),
  augustus alone on `bwrap` (codex-acp).
- Timeline confirmed: tip +72h = 2026-08-14T07:47:52Z; augustus's first corpus refusal was
  2026-08-14T23:35 — the first nightly run after the crossing. The night before he declined for
  board reasons at 63.8h. The fetch was already broken; the age crossing only made it visible.
- Host fetch succeeds today (exit 0), so once the snapshot path exists the gate goes green with
  `fetched: true` and `ref_age_hours: 644.5` — an accurate reading of a site nobody has published
  to, which is the correct outcome rather than a masked one.
- `augustus-content.service` is currently in `failed` state; it will re-arm on
  `augustus-content.timer` at 01:30 Europe/Amsterdam.
- `agent-workforce-auto-sync.timer` fires every 15 min and commits any dirty tree under a generic
  `Auto-sync:` message. Commit deliberately and promptly, or stop the timer for the batch.
