# Aurelian calibration pack — v2

**version: 2** · maintained by Dave · last changed 2026-08-13

Aurelian has no memory. This file is the only thing that carries a standard from one review to the
next, and the only channel through which a review can be corrected without editing the charter.
It is owner-maintained and static: Aurelian reads it, never writes it. He cites `calibration: v2`
and this file's digest in every verdict, so a verdict can be traced to the rubric that produced it.

Adding to it is how this agent improves. If a review produces a finding that should apply every
time, or a false positive that should stop recurring, it belongs here — bump the version.

**What this file may not do.** It refines rubrics and retry policy. It cannot override the charter,
expand filesystem authority, change verdict semantics, or authorize a prohibited action. A future
edit that appears to do any of those is a mistake in this file, not a new permission.

---

## Runtime policy — execution authority

**Pinned policy id: `host-noexec-v1`. Pinned attestation hash: NONE.**

There is no isolated runtime on this box today. Aurelian runs as `dave`, on the same account as
every agent whose work he reviews, so a test, a build script or a package install hook would run
with the fleet's privileges before anything has been judged.

Consequence, and it is deliberate: `/run/aurelian/runtime-attestation.json` does not exist, the
execution preflight in the charter cannot pass, and **every criterion requiring execution resolves
to INCONCLUSIVE**. Static inspection is the whole of the review until this changes. `runtime_policy:
host-noexec-v1` goes in the binding block.

This is not a degraded mode to be worked around. An attestation that appears without this file
pinning its hash is invalid by construction — the hash is pinned here, by the owner, or the
preflight fails.

**To turn execution on** (owner, once the Podman boundary is live): mount the attestation read-only
into the container, record its sha256 here as the pinned hash, give the policy a new id, and bump
this file's version. Three edits in one commit; no partial state.

## Binding — how the digests are computed

Every digest in the binding block is computed by Aurelian, from bytes he fetched himself. A digest
supplied by the submitter is a claim, and claims are what he is checking.

- `artifact_digest` — `sha256sum` of the exact file bytes; for a Notion page, of the fetched content
  snapshot, recorded together with `last_edited_time`.
- `diff_digest` — `git diff --binary <base>..<target> | sha256sum`. `N/A` for non-repository work.
- `criteria_digest` — `sha256sum` of the criteria document as fetched, at the revision cited.
- `calibration_digest` — `sha256sum` of this file.
- `review_id` — the root event id of the request thread, so a follow-up submission answering an
  INCONCLUSIVE can be tied to the review that asked for it.

---

## Rubric by artifact type

Aurelian selects the rubric from the artifact's **type and destination**, which the submission must
state. A submitter does not get to choose a rubric; if the type is missing, the verdict is
INCONCLUSIVE.

### Code / config — repositories under `~/dev`

- The project's `## Verification` block in its `CLAUDE.md` is the gate. Run it. Record each command
  and its exit status.
- **Exit code 0 is not evidence on this box.** Several wrappers here return 0 on a crash. Read the
  job's *output*, not its status. A run time pinned to a narrow band is a crash signature.
- A source edit is not a deployment. `agent-workforce` deploys through `bin/deploy`; nothing is
  automatic, and the deployed copy can carry drift the repo never saw. If a change claims to affect
  running behaviour, check the path it actually reaches.
- A config edit is inert until the process reloads it. Compare the file's mtime against
  `systemctl --user show <unit> -p ExecMainStartTimestamp` before accepting "fixed and verified".
- One concept, every site. A value that exists in three places and was changed in one is a finding
  even when the tests pass.

### Vault proposals — the inbox worktree

- Vault writes from this box are never direct. A proposal that has already written `vault/` is a
  FAIL on shape regardless of content.
- Check the claimed source document's date. Superseded vault documents do not announce themselves.
- Inserting prose re-cuts every chunk below it in the qmd index. A change to a long document is a
  retrieval change as well as a content change.

### Content drafts — LinkedIn, Notion Agent Content Inbox

- Against `content-writing-cause-effect-standard`: demonstrate the mechanism, cause to effect. A
  clever aphorism with no mechanism is a finding.
- Never villainize the buyer; frame behaviour as a rational response to incentives. End on the fix.
- Check for a duplicate row before accepting a new one. A hand-run draft can create a second
  Drafted row rather than advancing the Pitched one, and title-duplicate pairs suppress later
  pitching.

### Research / BD — Notion Agent Inbox rows, signal scans

- Every factual claim needs a source that can be opened. A confident sentence with nothing behind it
  is a finding, not a style preference.
- Vault-sourced claims: `query` ranks on wording, not recency. Cite the document *and its date*.
- A claim about a vendor, a price or a regulation that is not dated is unverifiable, not merely
  imprecise.

---

## Known-flaky checks — do not report these as defects

- **qmd returning nothing is usually retrieval, not absence.** Index paths use hyphens where disk
  uses underscores; `get` returns a `resource` block some clients drop; `multi_get` silently skips
  files over 10KB. Confirm with a second query shape before calling a document missing.
- **The `@@ -84,3 @@` header in qmd output is chunk-then-remainder, not a context window.**
- **A silent journal is not a dead service.** `buzz-agent@*` logs lifecycle only — never a line per
  message. Prove liveness with `CPUUsageNSec` against an idle sibling, not with log volume.
- **buzz-acp logs UTC; journalctl renders local (CEST, +2).** Normalise before building a timeline
  from both. An unnormalised offset has inverted cause and effect here before.

## Adjudicated — this is a finding

- A summary and a diff that disagree.
- An acceptance criterion with no corresponding change, even when everything present is correct.
- A verification command reported as passing that was not run.
- A file touched that the description never mentions.
- A `buzz messages send` at kind 9 aimed at a forum channel: receipted `ok`, shown to nobody.
- A second copy of a policy or a value that already has an owner elsewhere.

## Adjudicated — this is not a finding

- A different structure, naming or ordering than the reviewer would have chosen.
- Absence of a test the project's verification block does not require.
- A TODO or follow-up the author explicitly scoped out and named.
- Verbosity, tone, or comment density that matches the surrounding file.
- A missing feature that no acceptance criterion asked for.
