#!/usr/bin/env bash
# Finish-me script (NUC-09/NUC-10): run AFTER Dave registers the deploy key on
# github.com/Dave1524/obsidian-ai-os-boxsafe (Settings → Deploy keys → paste
# ~/.config/agent-workforce/keys/boxsafe_deploy.pub → ALLOW WRITE ACCESS).
#
# Idempotent: safe to re-run. Does: auth check → clone → confidentiality assert
# → agents/inbox branch + scoped worktree → qmd index + embed → exclusion tests
# → enable systemd services.
set -euo pipefail

VAULT="$HOME/vault"
WORKTREE="$HOME/agent-worktrees/inbox"
REMOTE="git@github-boxsafe:Dave1524/obsidian-ai-os-boxsafe.git"

echo "── 1. Deploy-key auth check"
# GitHub's `ssh -T` exits 1 even on success — capture output, never pipe under pipefail.
AUTH_OUT=$(ssh -o StrictHostKeyChecking=accept-new -T git@github-boxsafe 2>&1 || true)
if echo "$AUTH_OUT" | grep -q "successfully authenticated"; then
  echo "   OK: deploy key accepted by GitHub"
else
  echo "   BLOCKED: deploy key not registered yet ($AUTH_OUT). Register the public key first:"
  cat "$HOME/.config/agent-workforce/keys/boxsafe_deploy.pub"
  exit 2
fi

echo "── 2. Clone box-safe repo"
if [ -d "$VAULT/.git" ]; then
  echo "   already cloned — pulling instead"
  git -C "$VAULT" pull --ff-only
else
  git clone "$REMOTE" "$VAULT"
fi
git -C "$VAULT" config user.name "Praetorium Agent"
git -C "$VAULT" config user.email "agents@praetorium.invalid"

echo "── 3. Confidentiality assertion (release gate)"
CONF_HITS=$(find "$VAULT" -name "_confidential" -not -path "*/.git/*")
if [ -n "$CONF_HITS" ]; then
  echo "   FATAL: _confidential/ present in box-safe clone — STOP, tell Dave. Removing clone."
  rm -rf "$VAULT"
  exit 1
fi
echo "   OK: no _confidential/ anywhere in the clone"

echo "── 4. agents/inbox branch + scoped worktree"
if ! git -C "$VAULT" show-ref --verify --quiet refs/heads/agents/inbox; then
  if git -C "$VAULT" show-ref --verify --quiet refs/remotes/origin/agents/inbox; then
    git -C "$VAULT" branch agents/inbox origin/agents/inbox
  else
    git -C "$VAULT" branch agents/inbox
    git -C "$VAULT" push -u origin agents/inbox
  fi
fi
if [ ! -d "$WORKTREE" ]; then
  mkdir -p "$(dirname "$WORKTREE")"
  git -C "$VAULT" worktree add "$WORKTREE" agents/inbox
fi
mkdir -p "$WORKTREE/_inbox/agents"

echo "── 5. Verify main is push-protected for the deploy key (expect FAILURE)"
PUSH_OUT=$(git -C "$VAULT" push --dry-run origin HEAD:main 2>&1 || true)
if echo "$PUSH_OUT" | grep -qiE "protected|ruleset|denied|cannot|rejected"; then
  echo "   OK: push to main is blocked for this credential"
else
  echo "   WARNING: dry-run push to main was NOT rejected — check the repo ruleset before unattended runs"
fi

echo "── 6. qmd initial index + embeddings (first run downloads small GGUF search models)"
qmd update
qmd embed --timeout 25 || echo "   WARNING: embed hit timeout — re-run 'qmd embed' to finish"
qmd status

echo "── 7. Exclusion tests (release gate)"
INDEX_HITS=$(qmd ls vault 2>/dev/null | grep -i "_confidential" || true)
if [ -n "$INDEX_HITS" ]; then
  echo "   FATAL: _confidential paths in index: $INDEX_HITS"; exit 1
fi
if qmd get "_confidential/anything.md" >/dev/null 2>&1; then
  echo "   FATAL: qmd get served an excluded path"; exit 1
fi
echo "   OK: index clean, excluded paths fail safely"

echo "── 8. Enable services"
sudo systemctl daemon-reload
sudo systemctl enable --now qmd-mcp.service qmd-refresh.timer
systemctl --no-pager --lines=0 status qmd-mcp.service | head -3

echo ""
echo "ALL DONE. Warm-query latency check: time qmd query 'current priorities'"
echo "Next gates: OPENROUTER_API_KEY in secrets.env (NUC-08), then enable agent-proposal.timer (NUC-16)."
