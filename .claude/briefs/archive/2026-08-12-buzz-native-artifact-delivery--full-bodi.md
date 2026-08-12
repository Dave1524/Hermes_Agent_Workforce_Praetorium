# Brief: Buzz-native artifact delivery — full bodies, forum kinds, typed envelope, canvas

**Date:** 2026-08-08   **Verify:** `bash bin/verify.sh` (from repo root)

Source: Notion page *"Buzz-centric agent workforce review — findings and recommendations
(2026-08-08)"* (`3b68d768-1ede-8122-83a7-fdcfc76750ba`). Its "Implementation order" lists eight
items. This brief ships the four that are box-side implementable (**1, 2, 4, 6**) plus the concrete
fix the review's headline finding names, and records why **3, 5, 7, 8** are not shippable from
Praetorium. See *Out of scope* for the full accounting — none of the four is being silently dropped.

---

## Ground truth (verified this session — cite these, do not re-derive)

Two independent sources. **Upstream** = fresh shallow clone of `https://github.com/block/buzz` at
commit `02f640bc4559c48ac0c2ec595ef34dd2c294b0db` ("feat(desktop): unify add agent flows (#5015)").
**Deployed** = the binaries this box actually runs (`~/.local/bin/buzz`, build id
`a3688e512e8df7f547086620a0daa39ebbd4d522` per `docs/buzz-phase0-spike.md`). Neither binary answers
`--version`; upstream agreement is confirmed per-claim with `strings`, never assumed.

> **Clone note (2026-08-08).** That clone is gone; the one on disk at `/home/dave/REPOS/buzz` is
> `c71f658` ("Polish advanced agent setup and Welcome composer (#4926)", 2026-08-07) — *older*
> than the commit cited above. Every claim in the table was re-checked against it and every one
> holds; only line numbers shift (G3's `MAX_EVENT_CONTENT_BYTES` is at `ingest.rs:1919`, not
> `:1985`). **Locate these by symbol, not by line** — the line numbers are the perishable half of
> each citation, and a reader who greps the line and finds something else will wrongly conclude
> the claim was refuted.

| # | Claim | Upstream citation | Deployed confirmation |
|---|---|---|---|
| G1 | `--content -` reads the body from **stdin** | `crates/buzz-cli/src/validate.rs:168-179` (`read_or_stdin`), called at `crates/buzz-cli/src/commands/messages.rs:582` **before** size validation | `buzz messages send --help` → `Use '-' to read from stdin` |
| G2 | CLI content ceiling is **65,536 bytes** | `crates/buzz-cli/src/validate.rs:4` `pub const MAX_CONTENT_BYTES: usize = 65_536;`, enforced `validate.rs:64-73` | `strings` → `content exceeds maximum size (` |
| G3 | Relay ceiling is **256 KiB**, so the CLI is the binding constraint | `crates/buzz-relay/src/handlers/ingest.rs:1985-1992` `MAX_EVENT_CONTENT_BYTES = 256 * 1024` | `strings` → `content exceeds maximum size of ` |
| G4 | The relay **advertises** 65,536 in NIP-11 | `crates/buzz-relay/src/nip11.rs:226` `"max_content_len": 65536` | n/a (server-side) |
| G5 | `--kind` accepts **only 9, 45001, 45003** — anything else is a usage error | `crates/buzz-cli/src/commands/messages.rs:646-676`; the `Some(k) =>` arm returns `--kind {k} is not supported (use 9, 45001, or 45003)` | `strings` → `* is not supported (use 9, 45001, or 45003)` |
| G6 | 45001 = forum root, 45003 = forum comment and **requires `--reply-to`** | `crates/buzz-core/src/kind.rs:550-554`; `messages.rs:652-654` → `--reply-to is required for forum comments (kind 45003)` | `strings` → `--reply-to is required for forum comments (kind 45003)` |
| G7 | **The relay does not gate a content kind by channel type.** Forum kinds map to `Scope::MessagesWrite`, identical to kind 9; `channel_type` is read only on the kind:9007 channel-create path | `crates/buzz-relay/src/handlers/ingest.rs:372-374` (scope); `ingest.rs:2566-2640` (only `channel_type` site); `crates/buzz-core/src/channel.rs:59-95` (`ChannelType {Stream, Forum}`) | n/a (server-side) |
| G8 | Channel type is **not readable from this box** — `channels get` returns `{channel_id, created_at, description, name, pubkey}` and `channels list` the same, neither carries `type` | `crates/buzz-cli/src/commands/channels.rs` (`ChannelSummary`) | Ran live against `aceeddd2-…` (approvals) and `channels list --limit 20`: no `type` field in either |
| G9 | `canvas set` exists and takes stdin | `buzz canvas set` | `buzz canvas set --help` → `--content <CONTENT>  Canvas content (markdown; use '-' to read from stdin)` |
| G10 | The relay's Blossom store accepts **media only** — a `.md` artifact cannot be attached | `docs/buzz-phase0-spike.md` Proof 2 (verified live 2026-08-07) | unchanged |

### What G7 + G8 mean for the plan — read this before touching kinds

The review's item 2 assumes the four "forum routes" are forum-typed channels. **This box cannot
verify that** (G8), and `--type` is immutable after creation (memory:
`buzz-forum-channels-hidden-behind-experiments`). That looked like a plan-breaker — if
research/content/bd/approvals were created as `stream`, a kind-45001 root would be rejected and the
route UUIDs would need recreating.

**G7 defuses it.** There is no ingest path that rejects 45001 in a stream channel; forum kinds carry
the same write scope as kind 9. Channel type is a *client rendering* concern, not a relay
enforcement one. So:

- **Publishing 45001 is safe on every route regardless of type** — the relay accepts it.
- **Whether Desktop renders it as a thread is a Mac-side observation**, and is therefore an
  acceptance check Dave performs, not one this repo can assert. AC-19 records it as such.
- No channel recreation, no new UUIDs, no membership churn.

### Local findings the review is correct about

- `bin/deliver_proposal.sh:67` hands `deliver.sh` only `--message "$line"` where `line` is
  `PROPOSAL — proposed _inbox/agents/<date>_<slug>.md (Ns)`. The artifact never leaves the box.
  This is the headline finding, and it is exact.
- `bin/deliver.sh:37` `INLINE_MAX_BYTES="${BUZZ_INLINE_MAX_BYTES:-16384}"` — the 16 KiB ceiling is
  real. `bin/deliver.sh:346` builds `send_args=(messages send --channel "$channel" --content
  "$content")`, i.e. the body is one argv string; the in-file comment correctly notes
  `MAX_ARG_STRLEN` as the reason it cannot simply be raised.
- `bin/buzz_routes.env` carries six `ROUTE_<name>=<uuid>` lines and no kind information.

---

## Acceptance criteria

Numbered so the ship report can tick them individually. Each is either machine-checked by
`bash bin/verify.sh` (which runs every `tests/*.sh`) or explicitly marked as a human/Mac check.

### Transport — full bodies (review item 1)

- **AC-1** `bin/deliver.sh` passes the message body to the Buzz CLI on **stdin** (`--content -`),
  not as an argv string. Asserted by inspecting the mock helper's recorded argv: it contains
  `--content` followed by exactly `-`, and never the body text.
- **AC-2** The body the helper receives on stdin is byte-identical to the composed content
  (subject + envelope + artifact), verified by sha256 in the test, for a payload larger than the
  old 16,384-byte ceiling.
- **AC-3** A 40 KiB text artifact is delivered **whole** — no truncation notice appears in the
  transmitted body. (Pre-change this artifact was cut at 16 KiB; the review measured real proposals
  at 27–33 KiB, so this is the case that was failing in production.)
- **AC-4** The total transmitted content never exceeds **65,536 bytes** (G2). The artifact budget is
  computed as `65536 − len(subject + envelope + separators)`, so a long subject or envelope
  provably cannot push a maximal artifact over the CLI's limit.
- **AC-5** An artifact that exceeds the computed budget is still cut **on a line boundary**, remains
  valid UTF-8, and carries the `[truncated at N of M bytes — full artifact: <path>]` notice — the
  existing guarantees survive, only the ceiling moved.
- **AC-6** `BUZZ_CONTENT_MAX_BYTES` is overridable for tests but defaults to 65536, and a value
  above 65536 is rejected as a `config_error` rather than silently sent (the CLI would reject it
  anyway; failing early keeps the receipt category honest).

### Transport — forum kinds (review item 2)

- **AC-7** `bin/buzz_routes.env` declares a kind per route as `ROUTE_<route>_kind=<n>`. Values
  match the taxonomy already recorded in the archived `buzz-surface-migration` brief:
  `ops=9`, `signals=9`, `research=45001`, `content=45001`, `bd=45001`, `approvals=45001`.
- **AC-8** `bin/deliver.sh` resolves the route kind and appends `--kind <n>` to the send when the
  kind is not 9. Asserted from recorded argv for a forum route and its absence for a stream route.
- **AC-9** Only **9** and **45001** are accepted route kinds. `45003` is rejected with a
  `config_error` receipt naming the reason — no producer replies to an existing thread, and G6 makes
  45003 unusable without `--reply-to`. Any other value is likewise a `config_error`. This keeps the
  failure on our side of the boundary instead of surfacing as an opaque CLI usage error mapped to
  `transport_error`.
- **AC-10** A route with **no** `ROUTE_<route>_kind` line defaults to 9 and delivers exactly as
  before — adding the column is not a breaking change for any unported route.
- **AC-11** `tests/test_buzz_unit_wiring.sh` accepts `ROUTE_<route>_kind=` lines in the route table
  (its current assertion is that every non-comment line matches `^ROUTE_[a-z][a-z0-9_-]*=`) and
  additionally asserts that every declared kind is 9 or 45001, and that every `_kind` line names a
  route that exists.

### The headline fix — proposals carry their content

- **AC-12** `bin/deliver_proposal.sh` locates the proposal file that **this run** produced and hands
  it to `deliver.sh` with `--file`, so the proposal body reaches Buzz. The path is resolved from the
  inbox worktree (`$HOME/agent-worktrees/inbox`, overridable via `AGENT_INBOX_WORKTREE`) plus the
  `ts` and `proposal` fields of the run's own `cost.log` record — the same record `status_line()`
  already reads, so no new source of truth is introduced.
- **AC-13** A `NOPROPOSAL` run, a missing record, a record that predates the run marker, or a
  proposal file that is absent on disk **all** still deliver the existing status line as
  `--message`. The artifact path is an enhancement to the `PROPOSAL` case only; every decline path
  is byte-identical to today.
- **AC-14** The delivered artifact is anchored to this run: `deliver.sh`'s existing
  `--run-marker` check (`artifact -nt run_marker`) is exercised, and a stale proposal file produces
  an `artifact_error` receipt rather than a confident re-delivery of last night's work.

### Typed artifact envelope + supersession (review item 4)

- **AC-15** Every artifact-carrying delivery prepends a machine-parseable envelope to the body as a
  fenced ` ```yaml ` block containing exactly the nine fields the review names:
  `artifact_id`, `artifact_type`, `target`, `operation`, `content_sha256`, `base_revision`,
  `risk_tier`, `supersedes`, `acceptance_checks`.
- **AC-16** `artifact_id` is **deterministic** — the same job and artifact basename always produce
  the same id — and `content_sha256` equals the artifact's real sha256 (cross-checked in the test
  against `sha256sum` and against the `artifact_sha256` field already in the receipt).
- **AC-17** `supersedes` carries the Buzz event id of the previous delivery of the **same**
  `artifact_id`, or `none` on first delivery. State lives in one file (`$HOME/var/buzz-artifact-ids`,
  overridable), written only after a successful send, in the same idiom as the existing
  `PULSE_ROOT_FILE`.
- **AC-18** `risk_tier` defaults to `review` (human decision) and accepts only `auto|review|strict`.
  A caller cannot escalate a delivery to `auto` implicitly — the default direction is toward asking
  Dave, per the review's autonomy policy ("A second model's confidence score may route work but must
  not grant write authority").
- **AC-19** *(Mac-side, human check — cannot be asserted from this box.)* Dave confirms a delivered
  45001 root renders as a forum thread in Desktop on `#research`, and that the envelope block is
  legible above the artifact. If it renders flat, the channel is stream-typed (G8) and the decision
  is Dave's: accept flat rendering, or delete+recreate that channel as `--type forum` with a new
  UUID. Nothing in this repo changes either way.

### Canvas / living documents (review item 6)

- **AC-20** `bin/deliver.sh` gains `--canvas <off|mirror|only>` (default `off`) and is the **only**
  script permitted to invoke `buzz canvas set` — the existing single-transport-owner gate in
  `tests/test_buzz_unit_wiring.sh` is extended to cover `buzz canvas set` alongside
  `buzz messages send` / `buzz social publish` / `hermes send`.
- **AC-21** `mirror` writes the canvas **and** posts the channel message; `only` writes the canvas
  and posts neither the channel message nor the Pulse note. Both record a `canvas_result` field in
  the receipt (`ok|failed|unchanged|skipped`).
- **AC-22** Unchanged content does not churn: if the canvas content hash equals the hash recorded
  for that route's last canvas write, the write is skipped, `canvas_result=unchanged`, and the
  outcome is `delivered` — the review's "No new proposal when there is no material change", made
  mechanical.
- **AC-23** `bin/buzz_producers.tsv` gains a sixth column `canvas` ∈ `{none, mirror, only}`, and
  `tests/test_buzz_unit_wiring.sh` asserts (a) every row has six columns, (b) the vocabulary, and
  (c) **at most one producer per route** declares `mirror` or `only` — the review's "one designated
  writer" per canvas, enforced rather than remembered.
- **AC-24** `scorecard.service` is the ops canvas writer (`canvas=mirror`). It is the correct first
  case by construction: its unit already documents that the digest is idempotent and composed from
  current state at delivery time, with deliberately no run marker.

### Invariants that must survive (regression gates, all pre-existing)

- **AC-25** `bash bin/verify.sh` exits 0 — `bash -n` plus `shellcheck -S error` clean over every
  script in `bin/`, and every `tests/*.sh` green.
- **AC-26** The credential boundary is unchanged: `deliver.sh` still never names
  `BUZZ_PRIVATE_KEY`/`BUZZ_AUTH_TAG` in its own environment and still strips both from the helper's
  environment (`env -u BUZZ_PRIVATE_KEY -u BUZZ_AUTH_TAG`). The nsec appears in neither argv nor env
  in any new code path — including the new stdin path, where the body must not be echoed into a
  logged command line.
- **AC-27** Fail-soft by contract holds: every new failure mode (kind config error, canvas failure,
  budget overflow, missing proposal artifact) exits **0** and files exactly one categorized receipt.
  No new path can mark a work-producing unit failed.
- **AC-28** Discord independence holds: with `DELIVER_DISCORD=1`, Discord delivery is attempted and
  its result recorded regardless of every Buzz-side change, and `DELIVER_DISCORD=0` still suppresses
  it entirely.
- **AC-29** The offline-by-contract property of the Buzz tests holds: the PATH decoy still proves no
  real `buzz`/`hermes` binary is resolved, and no test contacts the relay.
- **AC-30** No producer's route assignment changes. The migration's dual-run posture
  (`bin/audit_buzz_dual_run.sh`, seven consecutive clean days before Discord may be disabled) is
  untouched by this brief.

---

## Files to modify

- **`bin/deliver.sh`** — the whole transport change lands here.
  - stdin body: write the composed content to `$workdir/content`, call
    `messages send --channel <uuid> --content -` with stdin redirected from it.
  - `CONTENT_MAX_BYTES="${BUZZ_CONTENT_MAX_BYTES:-65536}"` replaces the argv-derived ceiling;
    keep `INLINE_MAX_BYTES` **only** as an optional lower override so the existing
    `BUZZ_INLINE_MAX_BYTES` env knob keeps working. Artifact budget = `CONTENT_MAX_BYTES` minus the
    measured byte length of subject + envelope + separators.
  - `inline_artifact()` takes the budget as an argument instead of reading a global.
  - `resolve_route_kind()` alongside `resolve_route()`; `--kind` appended when != 9; validation to
    `{9,45001}` with a `config_error` fault otherwise.
  - `render_envelope()` emitting the nine fields; new optional flags `--artifact-type`,
    `--target`, `--operation`, `--base-revision`, `--risk-tier`, `--acceptance-check` (repeatable).
  - `artifact_id` + `supersedes` state file (`BUZZ_ARTIFACT_STATE`, default
    `$HOME/var/buzz-artifact-ids`), written only on a successful send.
  - `--canvas off|mirror|only` with the unchanged-hash suppression and a `canvas_result` receipt
    field; canvas content also goes over stdin.
  - New receipt fields: `kind`, `artifact_id`, `supersedes`, `canvas_result`.
- **`bin/deliver_proposal.sh`** — resolve this run's proposal path from the worktree + cost.log
  record; on `PROPOSAL`, hand `--file <path>` plus `--artifact-type vault-proposal`,
  `--operation create`, `--target <from the proposal's own front-matter, default none>`,
  `--base-revision <git -C worktree rev-parse --short HEAD>`; every other outcome keeps today's
  `--message` status line verbatim.
- **`bin/buzz_routes.env`** — add the six `ROUTE_<route>_kind=` lines and a header note explaining
  why kind is a route property (the review's "route-level event kinds") and why 45003 is excluded.
- **`bin/deliver_scorecard.sh`** — pass `--canvas mirror`.
- **`bin/buzz_producers.tsv`** — add the `canvas` column (`none` everywhere except
  `scorecard.service` = `mirror`); update the header comment.
- **`tests/test_buzz_unit_wiring.sh`** — six-column manifest, canvas vocabulary, one-writer-per-route,
  `ROUTE_<route>_kind` tolerated + validated, `buzz canvas set` added to the transport-owner gate.
- **`tests/test_buzz_deliver.sh`** — new cases for AC-1..AC-11, AC-15..AC-18, AC-20..AC-22, AC-26,
  AC-27. The mock helper must start recording **stdin** (`content.stdin`) in addition to argv.
- **`tests/test_buzz_adapters.sh`** — new cases for AC-12..AC-14.
- **`docs/runbook.md`** — a short subsection under the Buzz surface material: what the envelope is,
  where the kind table lives, which producer owns which canvas.

## Files to create

- **`docs/buzz-artifact-envelope.md`** — the normative envelope spec: the nine fields, their types,
  how `artifact_id` is derived, how `supersedes` chains, the `risk_tier` vocabulary mapped to the
  review's autonomy policy, and a worked example. This is the interface document the Mac-side broker
  (review item 5) will be written against, so it must be precise enough to implement from without
  reading `deliver.sh`.

## Test plan

TDD, in this order. Every test runs offline; none contacts the relay.

1. **Extend the mock helper** in `tests/test_buzz_deliver.sh` to capture stdin to
   `$MOCK_DIR/content.stdin` alongside the existing `argv.log` / `env.log`. Add a `stdin_body`
   helper. *Red:* nothing writes stdin yet.
2. **AC-1/AC-2/AC-3/AC-4/AC-5/AC-6** — stdin transport and the recomputed budget. The AC-3 case uses
   a generated 40 KiB artifact; assert no truncation marker and a sha256 match end to end. The AC-4
   case uses a deliberately long subject with a maximal artifact and asserts
   `len(stdin) <= 65536`.
3. **AC-7..AC-11** — route kind resolution. Table-driven over `{ops→absent, research→--kind 45001,
   bogus→config_error, 45003→config_error}`. Include the "no `_kind` line → behaves exactly as
   today" case, compared against a recorded baseline argv.
4. **AC-15..AC-18** — envelope rendering and supersession. Deliver the same artifact twice into a
   sandbox and assert the second body's `supersedes` equals the first delivery's
   `buzz_event_id` from the receipt. Assert `artifact_id` stability across the two runs and
   `content_sha256` equality with `sha256sum`.
5. **AC-20..AC-22** — canvas. Assert `mirror` produces two helper invocations
   (`messages send`, `canvas set`) and `only` produces one; assert the unchanged-hash second run
   skips the write and records `canvas_result=unchanged`.
6. **AC-12..AC-14** in `tests/test_buzz_adapters.sh` — a fake inbox worktree plus a synthetic
   `cost.log` record. Cases: `PROPOSAL` with the file present (`--file` passed, envelope fields
   correct); `PROPOSAL` with the file missing (falls back to the status line); `NOPROPOSAL`
   (unchanged); record predating the marker (unchanged).
7. **AC-23/AC-24** in `tests/test_buzz_unit_wiring.sh` — manifest shape and the one-writer rule;
   add a deliberately-broken fixture path only if it can be done without a second manifest file,
   otherwise assert against the real manifest.
8. **AC-26/AC-27/AC-28/AC-29** — re-run the existing credential-boundary, fail-soft, Discord and
   PATH-leak cases unchanged; extend the credential case to assert the nsec is absent from
   `content.stdin` too.
9. **AC-25** — `bash bin/verify.sh` green as the final gate.

Baseline for comparison: `bash bin/verify.sh` was run before any edit in this session and exited
**0**. A red gate after the change is therefore this change's fault, never pre-existing.

## Out of scope / do not touch

**Review items not shipped, and why.** These are not deferred by preference — each is blocked by a
credential or a gate this box does not hold.

- **Item 3 — reduce custom agent parallelism to 1, repair prompts and host ownership.**
  Desktop-side. The managed-agent records live on the Mac in
  `~/Library/Application Support/xyz.block.buzz.app/agents/managed-agents.json`; this box has no
  copy and no write path to it. The box-side units (`buzz-agent@*`) are a separate runtime that
  reads `~/.config/buzz-agents/`, which is deny-listed to every session here — even Bash. Dave must
  make this change from the Mac. *(Related and separately actionable: the review notes Trajan is
  running locally with ten workers while its prompt points at a box-only charter path — that is a
  doubled-hosting condition, and the tell is a doubled reply, not anything in the box journal.)*
- **Item 5 — the deterministic Mac broker.** It performs canonical writes and records
  proposed→approved→applying→applied/failed. This box holds no canonical vault credential (repo
  `CLAUDE.md`: "No canonical vault access"; only a repo-scoped deploy key to the boxsafe mirror) and
  vault promotion is Mac-gated by standing policy. **The box-side half of item 5 is item 4, and it
  ships here:** `docs/buzz-artifact-envelope.md` is written specifically as the broker's input
  contract, so the Mac work can start against a frozen interface.
- **Item 7 — retire the Notion Agent Inbox.** The review conditions it on parity tests. The
  operative gate is already recorded in the archived `buzz-surface-migration` brief: seven
  consecutive clean days of `bin/audit_buzz_dual_run.sh`. That clock has not run.
- **Item 8 — migrate scheduling into Buzz-managed agent execution.** The review conditions it on
  durable trigger/receipt behaviour being proven, which is items 1–6 landing first. Also blocked
  upstream: a relay-signed workflow message cannot wake an `--respond-to owner-only` agent
  (recorded in the archived brief with citations), and Buzz Workflow approval is unusable until
  WF-08 is fixed.

**Do not touch.**
- `~/.config/buzz-agents/**`, `~/.config/agent-workforce/**`, `~/.ssh/**` — deny-listed credentials.
  Nothing in this brief needs them; `bin/buzz_publish.sh` resolves them at runtime and that boundary
  does not move.
- `vault/`, `~/agent-worktrees/inbox/` **content** — `deliver_proposal.sh` reads a proposal file at
  runtime by design, but no vault content is to be read into a session transcript, and no vault file
  is edited by this work. Tests use a synthetic worktree.
- Route UUIDs in `bin/buzz_routes.env` — unchanged. No channel is created, deleted or retyped.
- Any live relay publish. This is a code + test change; the first real send happens on the next
  scheduled run, and the live canary is Dave's call.
- `bin/audit_buzz_dual_run.sh` and the dual-run posture.
- Do **not** weaken, skip or delete a test to make the gate green.

## Notes / preconditions

- **Deploy is not automatic.** `~/agent-workforce/` is the runtime systemd execs; source edits alone
  change nothing. After the gate is green, `bin/deploy` (rsync, atomic rename, additive) is the only
  correct way to promote — never a manual `cp`. The deployed tree can carry uncommitted drift, so
  diff before deploying. Deployment is a separate, explicitly-approved step and is **not** part of
  this brief's gate.
- **`agent-workforce-auto-sync.timer` fires every 15 minutes** and does `git add -A` + commit + push
  to `origin/main`. Commit this work immediately after editing or the message is lost to a generic
  `Auto-sync:` commit and unrelated WIP rides along. `git fetch origin` and compare against
  `origin/main` before committing — local checkouts here have been silently merged-and-stale before.
- **Stage by explicit path.** Never `git add -A` in this repo by hand.
- **Baseline confirmed:** repo clean on `main`, in sync with `origin/main`, `bash bin/verify.sh`
  exit 0, HEAD `9664ec8`.
- **The 65,536-byte ceiling is the CLI's, not the relay's** (G2 vs G3). If a future artifact needs
  more, the escape hatch is a NIP-23 long-form note (`buzz notes set --content -`, idempotent upsert
  keyed by `(author, slug)`, returns an `naddr`) with a pointer in the channel message — documented
  in `docs/buzz-phase0-spike.md`. That is deliberately **not** built here: 65 KiB covers the
  measured 27–33 KiB proposals with room to spare, and a second artifact surface is a second place
  for the review trail to drift.
- **`--file` still cannot carry a text artifact** (G10). The artifact reaches Buzz as message body
  or not at all; Discord keeps getting the attachment. Nothing in this brief changes that, and
  `is_media_artifact()` stays exactly as it is.

-> /clear then /implement
