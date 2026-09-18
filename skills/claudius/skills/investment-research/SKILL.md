---
name: investment-research
description: >
  Investment research distillation skill for Dave Hamelink. Turns external research (URLs, PDFs, analyst pieces,
  onchain data, books) into entries in a machine-queryable investment reasoning graph under 09_investing/ — not a
  flat archive of summaries. Every output links to canonical entity and framework notes, carries thesis-state and
  confidence metadata, surfaces a mandatory causal chain, and is forced to surface disconfirming evidence (skill
  performs WebSearch counter-search). Use when Dave says "/investment-research [URL or topic]", "research
  [analyst]'s latest on [topic]", "distill this PDF", "update the [TICKER] entity with [data]", or "expand the
  [TICKER] thesis from yesterday". Outline-and-ontology review gate before any write. Never executes trades, never
  recommends positions unprompted, never writes to Notion.
---

Canonical source: `08_skills/investment-research/SKILL.md` in the vault; its bundled files sit beside it in
`08_skills/investment-research/`. On this box: `~/vault/08_skills/investment-research/`

This file is a pointer, never a copy. Read the canonical SKILL.md first and resolve its
relative references from that directory. The description above is the vault's, mirrored by
bin/pointer_skills_sync.py so the trigger text an agent reads is the one the vault wrote.
