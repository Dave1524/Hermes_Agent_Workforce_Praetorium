# Buzz Phase 0 spike — verdicts

Deliverable for Phase 0 of `.claude/briefs/buzz-surface-migration.md`: one verdict per proof,
recorded against the deployed build rather than upstream source.

Spike run 2026-08-05 (setup) and 2026-08-07 (execution). All event times below are **UTC**, as
the relay records them; the box renders local time (CEST, +2).

## Deployed build under test

| | |
|---|---|
| `buzz` build ID | `a3688e512e8df7f547086620a0daa39ebbd4d522` (ELF, not stripped) |
| `buzz` sha256 | `2336205feb10b6e7323f73126ac879024c9964b209b47bd9b8bf68273a47033a` |
| Version flag | none — `--version`, `-V` and `version` are all rejected. Cite the build ID. |
| Relay | `vpc.communities.buzz.xyz` |
| Spike identity | `spike0`, pubkey `e76cab92f810f14addc1d8bed67c435cad4906ddfbe20583d541891753051bbd` |
| Throwaway channel | `spike-phase0`, `1e71019f-952b-4074-9e0d-3770a3c7ff53` |
| Owner | `82cfc202fce4103742578f8f23849eb616f7ef96ca59a1b13a70d720a9be616f` |

## Verdicts

| # | Proof | Verdict |
|---|---|---|
| 1 | Identity auth and channel membership from a non-interactive context | **PASS** |
| 2 | Channel text, attachment upload/render, returned event ID, exact Desktop pointer | **PASS** — with a design-changing finding |
| 3 | NIP-01 note rendering, Following behaviour, actual 300-second grouping | **PASS as measurement — REFUTES the plan's premise** |
| 4 | Relay-signed workflow messages do not wake an owner-only agent | **NOT RUN — still blocked on owner authority** |
| 4e | (substituted) end-to-end delivery through `bin/deliver.sh` | **PASS** — after one bug, fixed in `4244cb1` |
| 5 | Hosted workflows enabled; deployed relay revision | **BLOCKED** — owner/admin authority |
| 6 | Complete `request_approval → approve → resume → send_message` | **BLOCKED** — owner/admin authority |

Proofs 5 and 6 were never going to clear on a throwaway agent identity: `workflows create`
requires owner/admin authority, which a minted agent does not confer.

## Proof 1 — PASS

Auth and channel membership both succeed from a non-interactive context, via
`systemd-run --user --pipe --collect -p EnvironmentFile=<deny-listed .env>`. The private key is
loaded by systemd and never enters the agent's context. This is the exact indirection
`bin/deliver.sh` depends on, so proving it here proves the transport seam.

A read-only control as `marcus` through the identical harness succeeded first, isolating each
`spike0` failure to `spike0`'s own config rather than to the relay or the harness.

### Two credential-file traps found bringing spike0 up

- **systemd strips the inner double quotes from an unquoted value.** A raw
  `BUZZ_AUTH_TAG=["auth",...]` reaches `buzz` as invalid JSON and fails with
  `BUZZ_AUTH_TAG is malformed`. The value must be wrapped in single quotes.
  `check-loaded.sh` cannot see this.
- **A missing `BUZZ_RELAY_URL` does not error.** `buzz` silently falls back to
  `http://localhost:3000` and reports connection-refused as a `network_error`, which reads as a
  relay outage rather than a config gap. Copy the line verbatim from an existing agent `.env`;
  the CLI wants the `http(s)://` base URL, not the `wss://` form in `CLAUDE.md`.

## Proof 2 — PASS, and the payload contract changes

**The relay's Blossom store accepts images only.** Measured, not inferred:

- Rejected as `application/octet-stream`: `.md`, `.log`, `.txt`, `.json`, `.csv`, `.html`.
  The gate is content-sniffed magic bytes, so renaming does nothing.
- A real PDF is correctly identified as `application/pdf` and is **still** rejected. The
  allowlist is media types, not documents — no container format sneaks a report through.
- A genuine 1x1 PNG uploads fine and returns url/sha256/type/dim/blurhash/thumb.

Every text artifact this migration intends to deliver is therefore rejected at upload.
`--file <exact-path>` cannot carry any producer artifact.

**Replacement: NIP-23 long-form notes.** `buzz notes set --name <slug> --title <t> --content -`
takes a markdown body on stdin and returns event ID, `naddr` and a coordinate
`30023:<pubkey>:<slug>`. It is an idempotent upsert keyed by (author, slug), so a re-run of the
same job updates in place instead of duplicating — strictly better than attaching a fresh copy
of a file every night. The run-marker anchoring logic still applies; it now validates what gets
published as a note rather than what gets uploaded.

Proven live: coordinate
`30023:e76cab92f810f14addc1d8bed67c435cad4906ddfbe20583d541891753051bbd:proof2-artifact`,
note event `a94ff93e6a669a8e4cac8dec1c985efd7c40361e623e5b2f29bfdd082c6ceab6`, channel message
`6177f58fb5697d455827d46c533bbd25b932979c62e01c38b78a3d29645c1386` (image attachment rendered).

### Pointer form

Desktop's copy-link emits a query string, not the path form `deliver.sh` had frozen:

```
buzz://message?channel=<uuid>&id=<event-id>
```

The scheme is real but Desktop-side only, which is why no `buzz://` string appears in the CLI
binary. Both components are fixed width (36-char UUID, 64-hex event ID), so a pointer is always
exactly **127 bytes** — deterministic, so the note builder's reservation arithmetic needs no
runtime measurement. `BUZZ_NOTE_MAX_BYTES = 800` is confirmed viable: 800 minus 127 minus roughly
60 bytes of job/runtime attribution leaves about 600 bytes for headline and 2-4 digest lines.
Fixed in `bin/deliver.sh`, commit `744d886`.

## Proof 3 — the 300-second grouping premise is wrong

A timed ladder of five notes was published at the specified deltas and observed in Desktop:

| Note | Offset | UTC | Event |
|---|---|---|---|
| L1 | 0s | 06:47:13 | `89f54bfe4a93…` |
| L2 | +60s | 06:48:13 | `2d84ae05901a…` |
| L3 | +240s | 06:51:14 | `9e889abbf9f8…` |
| L4 | +301s | 06:52:15 | `9880f608b4ff…` |
| L5 | +600s | 06:57:14 | `190e3ef880b5…` |

**Pulse's everyone view has no time-based grouping at all** — it renders one card per note at
every interval, including 0s. There is no 300-second boundary to sit inside. §8 of the migration
plan assumed activity grouping would collapse an overnight sequence into a single card; it does
not.

### Proof 3b — the replacement mechanism

Replies nest under their root in Pulse, so a per-day root note plus `--reply-to` is what actually
makes a night of deliveries read as one card. Verified live: root `ad2bd7a6cf60…` (07:04:09) with
replies `5a0cc12c06bb…` (07:04:40) and `b16fe1c75a2a…` (07:05:40) both nesting correctly.

Implemented in `53d2c7e`. Root resolution is fail-soft: if publishing or reading back the root
fails, the note still publishes standalone rather than losing the delivery. `a119169` fixed an
unset local under `set -u` that killed the command substitution on the first run of any day — the
root was never published, every note went out standalone, and nothing surfaced an error anywhere.

## Proof 4 — not run as specified

The brief's proof 4 asks whether **relay-signed workflow messages wake an owner-only agent**.
Answering it needs `workflows create`, which needs owner/admin authority. No workflow was created,
so the question stands open, gated behind the same authority as proofs 5 and 6.

Two things the spike did establish that bear on it, neither sufficient:

- An agent is demonstrably live and answering in `spike-phase0` — `Fizz`
  (`30c4a35614ef…`, role `bot`) replied to owner messages there. The positive control the plan
  asked for exists.
- Neither of `spike0`'s proof-4 channel messages woke any agent. But those are agent-signed and
  carry no `p` tag, so they are not the case under test.

`Fizz` is a real relay identity on this workspace. Earlier notes describing it as a Desktop-only
persona with no relay presence are wrong.

## Proof 4e — end-to-end delivery, PASS

What ran under the name "proof 4" was an end-to-end transport proof: route table lookup,
credential helper, channel message, Pulse note threaded under the per-day root, JSONL receipt —
published by `bin/deliver.sh` with no human in the loop.

| Run | UTC | Channel event | Pulse root | Pulse note |
|---|---|---|---|---|
| First | 07:32:28 | `6c67343f56d8…` | `cabb434173e3…` | `d9d41c2a0aa1…` |
| Corrected | 07:37:17 | `361153422f9a…` | `474be2d6f992…` | `ec9ab56bbc83…` |

The first run exposed a bug. Bash ends `${VAR:-default}` at the first unescaped `}`, so the
literal `{date}` and `{channel}` in the two template defaults lost their closing brace: the day
root published as `Praetorium spike — 2026-08-07}` and the pointer read
`channel={channel&id=<hex>`. It corrupted a caller-supplied value too, not only the default.

Both existing assertions were substring greps and stayed green, because the stray brace lands at
the end of the string. Fixed in `4244cb1`, with new assertions anchored on exact values.

## Corrections to the migration plan

- **Channel creation needs no owner key.** Any relay member can create a channel, add members to a
  channel **it owns**, and delete it. §5's claim that channel creation and membership are
  owner-authority actions is wrong. Verified 2026-08-07 with the non-owner `spike0` identity:
  create, `add-member --role member`, delete, all `accepted:true`. Note the scope — this does *not*
  establish that a non-owner can add members to a channel someone **else** owns; that path has only
  ever been exercised with the owner key loaded. `channels create` also requires `--type` and
  `--visibility`, and `--type` is immutable after creation.
- **A new identity still needs the Mac, but an existing one's auth tag does not.** Admitting a
  brand-new identity to the relay requires the owner to sign its NIP-OA auth tag, so minting stays
  Mac-side. Once that identity has published *any* event, its tag is recoverable from the event's
  `tags` — `["auth",<owner-pubkey>,"",<sig>]`, a fixed attestation, not a per-event signature.
  `buzz social event --event <id>` (the flag is `--event`, not `--id`) requires channel membership;
  a non-member gets `events: 0` rather than an error. This is how `praetorium.env` was repaired on
  2026-08-07 after the tag was found empty. Do not confuse the tag with the event's top-level `sig`
  field — both are 128 hex chars, only the tag is a credential.
- **§6's file-attachment payload contract is void.** See proof 2 — artifacts become NIP-23 notes,
  and the channel message carries the pointer.
- **§8's 300-second activity grouping does not exist.** See proof 3 — a per-day thread root
  replaces it.
- **The credential helper is not a secret.** It resolves an identity slug to a credential file and
  execs `buzz`; only the `.env` files it reads need withholding. Keeping it under
  `~/.config/buzz-agents/` made it untracked, untestable and undeployable for no security gain.
  It now ships as `bin/buzz_publish.sh` (`4d5a4ac`), which clears the blocker recorded on
  2026-08-07.
- **`hermes cron disable` is not a subcommand.** The valid verb is `pause`. As written the command
  fails at the tail of an `&&` chain and silently leaves the retired job active.

## Still outstanding

- Proofs 4, 5 and 6 need owner/admin authority for `workflows create` and the
  `request_approval → approve → resume → send_message` cycle. Item 6 is expected to fail on the
  documented upstream implementation; record the result and keep approval workflows out of scope
  until it passes.
- Nothing is deployed. `deliver.sh`, `buzz_publish.sh` and `buzz_routes.env` exist only in the
  source tree — `~/agent-workforce/bin/` has none of them, and `~/logs/delivery-receipts.jsonl`
  does not exist, so no producer has yet delivered through the real path.
- Phase 2a remains gated on that deploy plus the unit installs.
