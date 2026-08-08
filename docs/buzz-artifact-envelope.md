# The Buzz artifact envelope

Normative spec for the block that `bin/deliver.sh` prepends to every artifact-carrying
delivery. `bin/deliver.sh` is the only producer; a Mac-side broker is the intended consumer.
Written to be implementable without reading `deliver.sh` — where the two disagree, this
document is wrong and should be corrected, but `deliver.sh` is what ships.

## Why it exists

An artifact posted as prose can be read but not *decided on*. A reviewer cannot tell from the
body whether this is the same proposal as last night's with two lines changed, what it would
overwrite if accepted, or whether the bytes they are reading are the bytes the run produced.
The envelope states those things in a fixed shape so a broker can identify, hash-check and
supersede a delivery without parsing the prose, and so a human's approval names one specific
artifact rather than "the one in that thread".

## Placement

The message content is, in order:

```
<subject line>
<blank>
<envelope block>
<blank>
<artifact body, or the status message>
```

The envelope is a fenced ` ```yaml ` block. It is present **only** when the delivery carries an
artifact (`--file`). A status-only delivery has no envelope and no body — subject and message
only. Everything after the closing fence is opaque to the broker.

## Fields

Nine keys, always all nine, always in this order. Values are JSON-encoded scalars (so a value
containing `:` or a newline cannot break the parse); `acceptance_checks` is a YAML list of
JSON-encoded strings, or `[]`.

| Field | Type | Meaning |
|---|---|---|
| `artifact_id` | 16 hex chars | Stable identity of this artifact *across deliveries*. See below. |
| `artifact_type` | string | What kind of thing this is. Producer-declared; default `report`. |
| `target` | path or `none` | The path this artifact proposes to write, relative to the vault root. `none` = it proposes nothing (a report, a digest, a draft pack). |
| `operation` | `create`\|`update`\|`none` | What the write would do to `target`. `none` whenever `target` is `none`. |
| `content_sha256` | 64 hex chars | sha256 of the artifact **file on the box**. See the truncation caveat. |
| `base_revision` | string | The revision the artifact was produced against, or `unknown`. Producer-declared. |
| `risk_tier` | `auto`\|`review`\|`strict` | How much authority a broker may exercise. Default `review`. |
| `supersedes` | event id or `none` | The Buzz event id of the previous delivery of this same `artifact_id`. |
| `acceptance_checks` | list of strings | What would have to be true for this to be accepted. May be empty. |

### `artifact_id` — derived, never minted

    artifact_id = sha256( "<job>" || NUL || basename(<artifact path>) )[0:16]

Deterministic by construction: the same unit re-delivering the same filename lands on the same
id on every run, across restarts, with no state involved. That is the point — an id drawn from a
counter or a timestamp breaks every supersession chain the first time the box reboots.

Two consequences to design around, both deliberate:

- It is keyed on the **basename**, so the same filename in two directories from the same job
  collides. Producers here write dated filenames into one directory per job, so this does not
  arise; a producer that changes that has to change this derivation with it.
- The date is usually *in* the filename, so a nightly job produces a **new** `artifact_id` each
  night and `supersedes` stays `none`. Supersession chains form for re-deliveries of the same
  named artifact — a corrected run, a retry — not for tonight's edition of a daily report. This
  is the correct reading: last night's report is not superseded by tonight's, it is history.

### `supersedes` — chained through one state file

`deliver.sh` keeps `artifact_id → last successful event id` in `$HOME/var/buzz-artifact-ids`
(tab-separated, one line per id, overridable with `BUZZ_ARTIFACT_STATE`). The mapping is written
**only after the channel send succeeds**, so a failed delivery never claims to supersede
anything and never becomes something to supersede.

The chain is therefore box-local. A broker must treat `supersedes` as a claim to verify against
the relay — fetch the named event, confirm its author and its `artifact_id` — not as proof.
Losing the state file loses the chain, not the artifacts: every id re-derives, and the next
delivery simply reads `supersedes: "none"` again.

Note that only the **channel message** records this mapping. A `--canvas only` delivery writes no
channel event, so it neither reads nor extends a chain.

### `content_sha256` — of the file, not necessarily of what you read

The hash covers the artifact as it exists on the box. The delivered body may differ in two
cases, and a broker must not report a mismatch as tampering without checking for them:

- **Truncation.** The Buzz CLI caps content at 65,536 bytes. An artifact that does not fit is cut
  at a line boundary and carries a `[truncated at N of M bytes — full artifact: <path>]` notice
  as its last line. The hash still describes the whole file, which is what makes it useful — it
  is how a broker knows it is holding a partial copy.
- **Media artifacts.** An image or PDF is uploaded to Blossom and attached; the body is then the
  producer's `--message`, not the artifact. The hash still describes the attached file.

For a text artifact under the ceiling and with no notice line, `sha256(body after the envelope
block and its trailing blank line) == content_sha256` holds exactly.

### `risk_tier` — defaults toward asking

- `auto` — a broker may apply this without a human decision.
- `review` — a human decides. **This is the default and no caller can reach `auto` by omission.**
- `strict` — a human decides, and the broker must additionally refuse to apply it unmodified
  (used for anything touching a boundary the box is not allowed to cross alone).

An invalid value is a `config_error` receipt and the delivery is skipped rather than sent at a
tier nobody chose.

## Worked example

A raw-ingest run that distilled one source:

````
[Praetorium] raw-ingest

```yaml
artifact_id: "9f2c41ab77e05d13"
artifact_type: "proposal"
target: "_inbox/agents/2026-08-08_raw-ingest.md"
operation: "create"
content_sha256: "4d7a1f0c9b62e58d3ac1f0e77b45d2903ec6118a5f4b0d29c7e8a316bd045f92"
base_revision: "unknown"
risk_tier: "review"
supersedes: "none"
acceptance_checks: []
```

# Distillation: <source title>
...
````

## What the broker may assume

- Exactly one envelope per message, and it is the first fenced block.
- All nine keys present. A message missing any of them was not produced by `deliver.sh` and
  should be ignored rather than guessed at.
- The author is the service identity in the receipt (`praetorium` today). The envelope carries
  no author field on purpose: `buzz messages send` does not echo the author back, so anything
  recording it from the publish response would record an empty string. Resolve the author from
  the relay by event id.
- `artifact_id` is stable; `supersedes` is a hint to verify; `content_sha256` is authoritative
  for the file and only conditionally for the body.

## What this envelope is deliberately not

**It is not kind 40008.** Buzz has one natively-typed, relay-validated artifact kind —
`KIND_STREAM_MESSAGE_DIFF` (40008), with its own CLI verb (`buzz messages send-diff`), its own
relay-side validator, and a `DiffPosted` workflow trigger. It is tempting, and it does not fit:
the relay validator **rejects an event missing a `repo` or `commit` tag**
(`crates/buzz-relay/src/handlers/ingest.rs`, `validate_diff_event`; upstream `c71f658`,
2026-08-07), and the CLI requires `--repo <url>` and `--commit <sha>` as non-optional parameters.
40008 is a *code diff anchored to a git commit*, not a general typed artifact. Vault proposals
are new markdown files with no upstream commit to diff against, so every 40008 field that
carries meaning would have to be faked.

The cost of not using it is real and should be stated: 40008 events are validated by the relay
and can trigger a Buzz workflow natively, while this envelope is validated by nobody and read by
a broker we have to write. That trade is taken because a faked `commit` tag would make the
relay's validation meaningless while looking like it worked.

If a producer ever delivers an actual patch against a real repo and commit, `send-diff` is the
right call for it and this envelope should not be stretched to cover it.

## Changing this spec

The envelope is an interface: `deliver.sh` writes it, a Mac-side broker reads it, and the two
ship on different schedules from different machines. Adding a field is safe if consumers ignore
unknown keys. Removing or re-typing one is not — the broker is not in this repo and will not
fail loudly. Version by adding, and pin any change here before it lands in `deliver.sh`.
