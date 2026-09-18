---
name: linkedin-review
description: >
  Monthly LinkedIn performance review for Dave Hamelink's personal page. Trigger whenever Dave says
  "LinkedIn review", "monthly LinkedIn review", "analyze my LinkedIn", "LinkedIn performance", or when
  a new `Content_*_DaveHamelink.xlsx` export is dropped in the LinkedIn_Posts folder. Parses the
  28-day LinkedIn export, maps posts to Notion Content DB drafts, compares to prior reviews, and
  produces a PM-style review (deviation / risk / action) written to Notion + vault.
---

Canonical source: `08_skills/linkedin-review/SKILL.md` in the vault; its bundled files sit beside it in
`08_skills/linkedin-review/`. On this box: `~/vault/08_skills/linkedin-review/`

This file is a pointer, never a copy. Read the canonical SKILL.md first and resolve its
relative references from that directory. The description above is the vault's, mirrored by
bin/pointer_skills_sync.py so the trigger text an agent reads is the one the vault wrote.
