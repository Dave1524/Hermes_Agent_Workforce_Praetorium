---
name: agent-inbox-sync
description: "Bridges the Praetorium box's agent write path (agents/* branches on the canonical vault repo) to a Notion review queue, so Dave can approve/reject agent work from Notion instead of the CLI. Two operations: (1) SYNC — surface pending agents/* branches in the Notion Agent Inbox database as Status=New rows; (2) PROCESS — for rows Dave set to Approved, merge the branch into canonical main via agent_branch.py (guarded: conflict + new-lint-violation preview), land a full-content readable copy in the Notion Box Output database, and flip to Status=Promoted; for Rejected rows, agent_branch.py reject with the Notes field as reason. Use when Dave says 'sync agent inbox', 'check the agent inbox', 'process approved proposals', 'anything new from the box', or at the start of a session as part of morning-startup's overnight check. PROCESS also runs unattended hourly via agent_merge_watch.sh for clean single-target branches only — Dave stays the approval gate."
---

Canonical source: `08_skills/agent-inbox-sync/SKILL.md` in the vault; its bundled files sit beside it in
`08_skills/agent-inbox-sync/`. On this box: `~/vault/08_skills/agent-inbox-sync/`

This file is a pointer, never a copy. Read the canonical SKILL.md first and resolve its
relative references from that directory. The description above is the vault's, mirrored by
bin/pointer_skills_sync.py so the trigger text an agent reads is the one the vault wrote.
