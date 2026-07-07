# Vault agent branch / inbox workflow (NUC-11) + review from the Mac (NUC-17)

**Mechanics decision (PROPOSED, awaiting ratification): hybrid — an `agents/inbox` branch that
only ever contains files under `_inbox/agents/`.** Branch gives isolation + one-command review;
the folder convention makes every proposal self-describing and keeps the eventual promotion step
(a copy into the canonical vault) trivial.

## How it works

- The box holds TWO checkouts of the box-safe repo (`Dave1524/obsidian-ai-os-boxsafe`):
  - `~/vault` — `main`, read-only context. qmd indexes this. Agents never write here.
  - `~/agent-worktrees/inbox` — git worktree on branch `agents/inbox`. The ONLY writable checkout.
- Agents write proposals as `_inbox/agents/YYYY-MM-DD_<slug>.md` (structured: summary, evidence,
  proposed vault change, target canonical file).
- `agent_propose.sh` enforces the boundary: any diff outside `_inbox/agents/**` aborts the run and
  hard-resets the worktree. API failure → no commit, no push (no garbage proposals).
- Credential: a deploy key scoped to the box-safe repo only (minimal GitHub permission — no
  account-level PAT). A repo ruleset blocks the deploy key from pushing `main`; Dave (admin)
  bypasses, so the Mac-side mirror sync keeps working.

## Review / promote / reject from the Mac (NUC-17 — Dave's loop)

```bash
cd ~/dev/obsidian-ai-os-boxsafe   # or any clone of the box-safe repo
git fetch origin agents/inbox
git diff main...origin/agents/inbox -- _inbox/agents/   # inspect (Claude can assist)
```
- **Promote:** apply the proposal's content to the canonical vault (`~/dev/obsidian-ai-os`) as a
  normal Claude-assisted edit — the proposal file itself never merges to canonical. Then delete
  the proposal file from `agents/inbox` (commit "promoted: <slug>").
- **Reject:** delete the proposal file with a one-line reason in the commit message
  ("rejected: <slug> — <why>"). The reason flows back to the agent's next qmd context refresh.
- Canonical vault stays clean: nothing on the box ever pushes to the canonical repo — promotion
  is always a human/Claude action on the Mac.

## Why not PRs?

The box-safe repo is a generated mirror; merging agent branches into its `main` would be
overwritten by the next mirror push. The inbox branch is a message queue, not a merge target.
