#!/usr/bin/env bash
# gh as the GitHub App (praetorium-vault-writer): mint an installation token through the
# same credential helper git pushes with, and hand it to gh in its environment only.
#
# Why a wrapper and not `gh auth login`: gh's keyring entry on this box is Dave1524, and a PR
# he opened is one he cannot approve. Every PR the box opens or merges — the ship-dev-plan
# land phase, the Control Room's schedule and retire proposals — goes through here so the
# author is <app>[bot] and the approval is his.
set -euo pipefail

HELPER="${GH_APP_HELPER:-$HOME/.local/bin/github_app_credential.py}"

refuse() {
  echo "gh_app: $1 ($HELPER)" >&2
  exit 2
}

[ -f "$HELPER" ] || refuse "no GitHub App credential helper at that path"

token=$(printf 'protocol=https\nhost=github.com\n' | python3 "$HELPER" get | sed -n 's/^password=//p')
[ -n "$token" ] || refuse "the helper minted no installation token"

GH_TOKEN="$token" exec gh "$@"
