# Task: write one Phase-B implementation brief

You are writing an implementation brief for the `agent-workforce` repo on Praetorium. The brief
id is in `$PHASEB_BRIEF_ID`. You write exactly one brief and then stop.

## STEP 0 — idempotency

If the output file already exists, print `skip: <path> already exists` and exit 0 without
writing. A re-fire must never clobber a brief a human has started reviewing.

## What to read, in this order

1. `design/phaseb-brief-queue.toml` — find the `[[brief]]` entry whose `id` matches
   `$PHASEB_BRIEF_ID`. Its `must_carry` lines were measured on 2026-09-01 and are either absent
   from the design docs or contradict what those docs still say. **Every one of them must appear
   in the brief you write.** They are the reason this queue exists: you are running cold, and the
   session that scheduled you knew things the repo does not record yet.
2. `design/open-decisions.md` — the section named by the entry's `section` field, plus
   `## Phase-B brief order` and `## Carried work`.
3. `.claude/briefs/fleet-guard-suite-connector-deny.md` — the brief for Phase-B item 1, already
   implemented. **This is your template.** Match its section order and its level of specificity.
4. Whatever source files the decision names. Read them; do not infer their contents.

## Shape of the output

Same seven sections as the template, in this order:

    # Brief: <imperative title>
    ## Acceptance criteria      numbered, each independently checkable
    ## Files to create
    ## Files to modify
    ## Test plan                what fails before the change exists, and how
    ## Out of scope / do not touch
    ## Notes / preconditions

Write it to `.claude/briefs/<slug>.md` using the entry's `slug`. **Do not write or touch
`.claude/briefs/current.md`** — that file is the pointer `/implement` reads, and choosing what
is current is Dave's call, not yours.

## Rules that are easy to get wrong

- **A brief describes WHAT, not HOW.** Acceptance criteria, boundaries and traps. Do not write
  the implementation, do not paste finished code, do not create the files the brief describes.
- **If the entry says `ships = "red"`, say so in the brief and name what is red on arrival.**
  A check that passes the moment it lands has not been shown to detect anything.
- **Never propose weakening a test or a gate to make something pass.**
- **A negative rule is asserted by absence of capability, never by attempting the action.**
  No brief may instruct anyone to send an email, push to a vault `main`, or use `--no-verify`
  in order to prove a guard works.
- **Carry preconditions forward as blockers, not assumptions.** If the entry lists a
  precondition that is a human action, the brief states it is unmet and stops there.
- **Cite `path:line` for any mechanical claim you make about this repo.** An uncited claim in a
  brief becomes an uncited claim in an implementation.
- Respect `CLAUDE.md`. The box holds no outward credential and takes no outward action.

## Finish

Print the path you wrote and a one-line summary. The wrapper handles commit and push.
