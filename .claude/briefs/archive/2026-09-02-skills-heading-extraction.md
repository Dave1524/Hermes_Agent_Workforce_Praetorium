# Brief: Replace augustus's pinned line-range skill extraction with heading-anchored extraction, and gate it with a test
**Date:** 2026-09-02   **Verify:** `bash bin/verify.sh` from the repo root (syntax + `shellcheck -S error` over `bin/`, then every `tests/*.sh`)

This is Phase-B brief 4, and it is **D3 part 1 only**. Part 2 — pointer skills under
`~/.claude/skills/` — is a separate, independent unit of work and is **out of scope here**:
`design/open-decisions.md:891` says part 1 "is the live defect and should not wait on part 2
(pointer skills), which is independent". Do not couple them. A change that registers pointer
skills does not touch the defect this brief fixes, and vice versa.

**The augustus extraction bug is the concrete failing case, and the test is written against it
first.** `profiles/augustus_content_task.md:74` reads the 453-line, 37,631-byte vault skill by
six pinned line ranges. Three of the six no longer land on the sections the profile says they
land on (measured 2026-09-02, table in Notes). Nothing errors, no suite covers it, and the pins
live in this repo while the file lives in the vault — two repos with no shared gate, so no commit
here can ever see the target move. **The test is that shared gate.** Write it, watch it go red
against the profile as it stands today, then fix the profile.

Read `design/open-decisions.md` D3 (line 214, decision at 283-291) before starting. This brief
does not restate its measurement — it states what to build, and corrects the two places where
D3's own record is now wrong.

## Acceptance criteria

1. **No line numbers anywhere in the extraction.** `profiles/augustus_content_task.md` names the
   sections it wants by their **heading text as it appears in the file**, and resolves them at
   read time. The string `sed -n '19,36p;…'` (`profiles/augustus_content_task.md:74`) is gone,
   and so is the sentence that calls the line ranges "the whole point" (`:78-79`).
2. **A section that does not resolve aborts the run; it never degrades it.** Unresolved means
   either *absent* (no heading matches) or *ambiguous* (more than one does). Both exit non-zero,
   name the offending section on stderr, and emit **no** section text at all — not the sections
   that did resolve. A partial skill read is the failure this brief exists to end; shipping 8 of
   9 sections silently is the same defect wearing a different mask.
3. **Augustus stops rather than drafts on that abort, and says why.** His reply names the
   unresolved section. It must not be indistinguishable from a normal "nothing to draft
   tonight" — the dispatcher already separates "nobody was asked" (4) from "asked and produced
   nothing" (1) from "board moved or `DECLINE:`" (0) (`bin/run_content_via_buzz.sh:10-14`), and a
   broken skill read that lands as an ordinary quiet night is a fourth outcome none of those
   three describe.
4. **A section carries its subsections.** Extent is the heading line through the line before the
   next heading of the **same or higher** level. `## Variations mode` (a `##` under `###`
   siblings) is the case that breaks a naive "stop at the next `###`" rule, and `### Step 4` is
   the case that breaks a naive "stop at the next blank line" one.
5. **Matching is on the whole heading, never a prefix.** `Step 2.5` is a prefix of `Step 2.55`,
   and `Step 5` of both `Step 5.5` and `Step 5.6`. A prefix matcher over-matches silently and
   would re-import exactly the Figma machinery the profile deliberately excludes
   (`profiles/augustus_content_task.md:94-96`).
6. **The extracted text equals the sections as measured, byte for byte.** Concretely, against the
   file as it stands today it must **contain** all three lines the current pins drop — self-check
   item 11 (`11. **AI-tell scan**`), the first-comment bullet `- Bridge to the adjacent audience
   without hijacking the post.`, and `- Recommended N: 3 (more than 5 is decision fatigue)` — and
   must **not** contain the two lines the current pins wrongly inject: the Step 5.6 `**Codex
   sandbox note:**` paragraph and archetype C's `Out of scope for this skill …` line.
7. **Still one command.** The profile reads the procedure in a single invocation, as it does
   today (`profiles/augustus_content_task.md:73`). This job runs under an explicit turn budget
   ("a few focused queries, then WRITE", `:29`); nine reads for nine sections spends it on
   plumbing.
8. **The mechanism lives where the gate can see it.** `bin/verify.sh:13-26` collects every script
   in `bin/` for `bash -n` (`:29`) and `shellcheck -S error` (`:33`); **nothing in this repo ever
   parses, lints or executes a shell line embedded in profile markdown.** That asymmetry is why
   the pins rotted unobserved for weeks. The extractor is a script under `bin/`; the profile
   calls it.
9. **`tests/test_content_skill_extract.sh` exists** and asserts that every section the profile
   names resolves to exactly one heading in the live vault file, that the extractor is fail-loud
   on both absent and ambiguous names, and that the profile and the extractor agree on the
   section list (no section named in one and not the other).
10. **The suite ships red and is observed red.** See "what is red on arrival" below. Do not land
    the profile fix and the test in one step and report a green gate — a check that passes the
    moment it lands has not been shown to detect anything.
11. **`design/agents/augustus.toml` records the new suite.** The `augustus-content` entry's
    `suite` list (`design/agents/augustus.toml:73`) gains `tests/test_content_skill_extract.sh`.
    This is the R15b declared join (`design/agent-model.md:144-172`) and it is what stops brief
    3's coverage checker from reading the new suite as an orphan.
12. **The runtime copy is updated.** The job reads
    `$HOME/agent-workforce/profiles/augustus_content_task.md`
    (`bin/run_content_via_buzz.sh:36`), not this repo. `bin/deploy` ships `bin` and `profiles`
    (`bin/deploy:20`) and **nothing deploys automatically** — an undeployed fix leaves augustus
    running the pinned ranges tonight.
13. **D3's own record is corrected in place, with today's date.** Two corrections, both measured:
    three of six ranges are wrong, not two; and `augustus_polish_task.md` has no pinned ranges to
    fix at all. Details in Notes.
14. `bash bin/verify.sh` exits 0.

## Files to create

- **A section extractor under `bin/`** — suggested `bin/skill_sections.sh`; the name is the
  implementer's call, the directory is not (criterion 8). Contract, not implementation: it takes
  a markdown file and a list of section names, prints each named section in **file order** with
  its heading line included, and on any unresolved or ambiguous name prints the name on stderr
  and exits non-zero having printed **nothing** on stdout. Nine sections in, nine sections out or
  nothing at all.

- **`tests/test_content_skill_extract.sh`** — the gate. See Test plan.

No new fixture files. The negative cases (absent heading, ambiguous heading, prefix collision)
are cheaper as `mktemp` fixtures inside the suite than as checked-in files, and `bin/verify.sh`
already owns one temp root for the whole run (`bin/verify.sh:43-45`).

## Files to modify

- **`profiles/augustus_content_task.md:73-79`** — replace the pinned `sed` with the named-section
  call. Keep the sentence that follows it honest: `:76-78` currently enumerates the sections in
  prose *alongside* the line numbers. After this change that prose list and the argument list are
  the same list stated twice — collapse to one, or the next drift is between them rather than
  against the vault.
  Also `:94` — "The sed range omits Mac-only machinery" describes a mechanism that will no longer
  exist. The exclusions themselves (Figma Steps 5/5.5/5.6 and the archetypes, Step 7's Notion
  write protocol, Step 8) stay exactly as they are; only the reason they are excluded changes
  from "outside the line ranges" to "not named".
  Add the abort behaviour of criterion 3 to the profile, in the profile's own imperative voice.

- **`design/agents/augustus.toml:73`** — add the new suite path to `augustus-content`. Note that
  `augustus-content` and `content-change-dispatch` are two triggers on one workflow sharing one
  profile (`design/agents/augustus.toml:74-78`, `bin/content_change_dispatch.sh:25`); the suite
  belongs on the entry that owns the profile, and duplicating it onto both is a second place to
  forget.

- **`design/open-decisions.md`** — the D3 drift table at `:271-274` and the decision at `:283-291`.
  Record the corrections of criterion 13 as dated additions. **Do not rewrite the 2026-09-01
  measurement** — it was right about the two ranges it named; it was incomplete, and the way that
  gets caught next time is by leaving both readings visible with their dates.

## Test plan

One file, `tests/test_content_skill_extract.sh`, following `tests/test_fleet_guards.sh`
verbatim in shape: `set -uo pipefail` (`:20`), the `assert()` helper that scopes `pipefail`
**off** inside the condition (`:39-45`), and `assert 'a found pattern is never reported as a
failure' "yes | grep -q y"` as the first assertion (`:49`). That canary is load-bearing, not
decoration — under `pipefail` a condition ending in `grep -q` fails a true assertion and silently
passes a negated one, which cost this gate one run in seven until 2026-08-09 and disabled every
`no artifact attached`-style assertion while it did.

Four groups:

1. **Every named section resolves, in the live file.** For each section the profile names:
   exactly one heading matches, on the file the job actually reads — resolve `~/vault` with
   `readlink -f` and assert against the resolved path (it is a symlink to the box-safe mirror
   today and repoints at cutover; the test must follow it, never hardcode either side). This is
   the assertion that fails the day someone renames a heading in the vault, which is the whole
   reason the suite exists.
   **A missing vault file is a FAIL, never a skip.** A suite that goes quietly green when its
   subject is absent is the failure mode this repo keeps rediscovering.
2. **The extractor is fail-loud.** Against `mktemp` fixtures, not the live file: an absent
   section name exits non-zero with empty stdout; a name matching two headings exits non-zero
   with empty stdout; a name that is a strict prefix of another heading (`Step 2.5` against a
   fixture carrying both `Step 2.5` and `Step 2.55`) resolves to the exact one or fails — never
   silently to both.
3. **Content, positive and negative, against the live file.** The extraction contains the three
   lines the old pins dropped and does not contain the two they injected (criterion 6). These are
   the assertions that would have caught the drift, and they are what makes group 1 more than a
   spell-checker.
4. **Profile and extractor agree.** The set of sections named in
   `profiles/augustus_content_task.md` is exactly the set the extraction call passes. A section
   the profile promises in prose but never extracts is the drift of criterion 6 rebuilt inside
   one file.

**What is red on arrival** — the entry declares `ships = "red"`, and this is what is red:
groups 1 and 3 fail against `profiles/augustus_content_task.md` **as it stands today**, on three
of six ranges (`168,235p`, `341,353p`, `414,423p`). Write the suite first, run
`bash bin/verify.sh`, and read the failures — they should name self-check item 11, the
"Bridge to the adjacent audience" bullet, and "Recommended N: 3". If the suite is green before
the profile is touched, it is asserting something other than the defect and must be rewritten,
not accepted. **Then** fix the profile and watch the same assertions go green. Red → green →
commit, in that order.

The gate needs no change: `bin/verify.sh:47-51` already runs every `tests/*.sh`.

## Out of scope / do not touch

- **D3 part 2 — pointer skills.** No `~/.claude/skills/` entries, no `SKILL.md` pointers, none of
  the 14-row persona table at `design/open-decisions.md:298-304`. Independent by decision
  (`:891`, `:317`). It is tempting because it is in the same section of the same document; it is
  a different unit of work and it does not touch this defect.
- **The vault file itself.** Do not edit
  `08_skills/linkedin-content-engine/SKILL.md` — not in the mirror, not in the canonical clone.
  The box holds no canonical vault credential, `main` in the mirror is machine-published from the
  Mac, and any vault change from here is a proposal under `_inbox/agents/**`. **Fixing an
  extraction by moving its target is not fixing it.** If a heading genuinely needs to change,
  that is a separate proposal and this gate should go red first.
- **`profiles/augustus_polish_task.md`.** D3's decision says to fix it too
  (`design/open-decisions.md:284`); measured 2026-09-02, it has nothing to fix — it reads
  `references/voice.md` and `references/ai_tells.md` **in full**, by exact path, with no line
  pins (`profiles/augustus_polish_task.md:26-28`). Leave it. Do not convert a whole-file read
  into a section extraction to make the two profiles symmetric.
- **`design/fleet-suites.toml`.** The new suite is owned by a *workflow* and belongs in that
  workflow's `suite` list. `fleet-suites.toml` is for suites no workflow can claim
  (`design/eval-spec.md:202-217`); adding a workflow-owned suite there gives it two owners and
  hands brief 3's checker an ambiguity to resolve.
- **Widening the suite to every path the profile names.** The seven `references/*.md` files, the
  published-corpus helper, `linkedin_shape.md` — all real, all currently resolving, all a later
  and larger question. This brief closes the drift that is live.
- **Mirror currency.** "Is the vault mirror up to date?" has exactly one owner,
  `bin/vault_sync_guard.sh` (`CLAUDE.md`, Daily rhythm jobs). This suite asserts section
  resolution against whatever `~/vault` currently resolves to and stays out of that question.
- **`~/vault` as a recorded path in any unit, config or worktree pointer.** It is a symlink;
  resolve it at read time. Recording it into anything that must survive cutover is a
  machine-level rule (`~/CLAUDE.md`, Top-level layout).
- Brief 2's drift check and brief 3's coverage checker. Neither is a prerequisite here and
  neither is a place to put any of this.

## Notes / preconditions

**No blocking preconditions.** The queue entry lists none, and nothing in this brief waits on a
human action. Deploy (criterion 12) is the one step that is easy to skip and invisible when
skipped.

Measured on the box, 2026-09-02, against
`~/vault/08_skills/linkedin-content-engine/SKILL.md` — 453 lines, 37,631 bytes, mtime
2026-08-14 18:44, unchanged since D3 measured it:

| pinned range (`profiles/augustus_content_task.md:74`) | intended section(s) | actual extent | consequence |
|---|---|---|---|
| `19,36p` | Hard non-negotiables | 19-36 | exact |
| `53,78p` | Step 1 — voice | 53-78 | exact |
| `100,134p` | Step 2.5 + Step 2.55 | 100-134 | exact |
| `168,235p` | Step 2.7 + Step 3 + Step 4 | 168-236 | **drops line 236 — self-check item 11, the AI-tell scan** |
| `341,353p` | Step 6 — first comment | 343-355 | opens on Step 5.6's Codex sandbox note (341); drops 354-355, incl. "Bridge to the adjacent audience without hijacking the post." |
| `414,423p` | Variations mode | 416-425 | opens on archetype C's "Out of scope for this skill" line (414); drops "Recommended N: 3 (more than 5 is decision fatigue)" |

- **Three of six are wrong, not two.** D3's table (`design/open-decisions.md:271-274`) names the
  last two. The `168,235p` miss is a third, and it is the most consequential of them: the profile
  itself tells augustus that `ai_tells.md` carries "11 structural AI tells + the de-slop pass +
  **self-check #11**" (`profiles/augustus_content_task.md:84`) while the extraction has been
  handing him a Step 4 that stops at item 10. The profile promises a check the skill read
  silently withholds.
- **Heading inventory:** 27 headings, all matching `^#{1,3} `, all unique. `## Hard
  non-negotiables` and `## Variations mode` are `##`; the nine Steps and three archetypes are
  `###`.
- **Copy heading text out of the file; never retype it.** Every Step heading uses an em dash
  (`—`, U+2014). A hyphen substituted for one matches nothing — which under criterion 2 is a
  loud abort rather than a wrong answer, so the failure is cheap, but it is a failure you can
  avoid entirely by copying.
- **Code fences are a latent hazard, not a live one.** 8 fence lines today and **zero**
  `#`-leading lines inside any fenced block, so a fence-blind matcher is green today and wrong on
  the first fenced example whose line starts with `#`. Worth handling; not worth blocking on.
- **The two vault copies are byte-identical today.** `~/vault` resolves to
  `~/dev/obsidian-ai-os-boxsafe`; `diff -q` against
  `~/dev/Obsidian_AI_Operating_System/08_skills/linkedin-content-engine/SKILL.md` is silent
  (both 37,631 B). So there is no divergence to reason about right now — but the job reads the
  **mirror**, and the mirror is published from the Mac. A heading renamed canonically and not yet
  published fails this gate. That is the correct direction: the gate should describe what
  augustus actually reads.
- **The deployed profile is in sync with source today** (`diff -q` silent between
  `profiles/augustus_content_task.md` and `~/agent-workforce/profiles/augustus_content_task.md`,
  both carrying the pins at line 74). It will not stay that way through this change without
  `bin/deploy`.
- **Augustus's namespace can reach both a new `bin/` helper and the vault.**
  `/usr/local/bin/codex-acp:25` is `--dev-bind / /`, and its tmpfs list (`:26-29`) covers
  `~/.ssh`, `~/.config/buzz-agents`, `~/.config/agent-workforce` and `~/.codex` — not
  `~/agent-workforce` and not `~/vault`. He already runs
  `python3 ~/agent-workforce/bin/notion_rest.py` from inside it
  (`profiles/augustus_content_task.md:68`), which is the same reachability this needs.
- **Do not add a fallback to line numbers** if a heading fails to resolve, and do not soften the
  abort into a warning to get a run through. The whole defect being fixed is a read that
  succeeded while returning the wrong thing.
- **Never `--no-verify`, and never weaken an assertion to make the gate green.** If group 1 goes
  red because the vault moved, the fix is a corrected section name or a vault proposal, not a
  loosened matcher.
- **No outward action is involved anywhere in this brief.** The box holds no outward credential;
  the extraction is a local read and the test is a local read.
- Commit as soon as each coherent piece is done — red suite first, then the profile fix.
  `agent-workforce-auto-sync.timer` fires every 15 minutes and commits any dirty tree with
  `git add -A`; work left uncommitted gets swept into a message that describes something else,
  and here that would erase the one commit that proves the test was red before it was green.
