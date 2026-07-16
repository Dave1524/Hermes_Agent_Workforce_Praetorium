#!/usr/bin/env bash
# NUC-42: Per-profile skills allowlist (prompt trim).
#
# Replaces the shared 147-skill / ~6MB external tree that every Hermes profile
# indexes (skills.external_dirs = [~/.hermes/shared-skills]) with a role-scoped
# subset of shared-skills SUBDIRECTORIES, and adds a skills.disabled denylist to
# hide irrelevant LOCAL per-profile skills. Both are OFFER-time filters only:
# nothing is deleted, every skill stays loadable via skill_view(name).
#
# This edits the LIVE ~/.hermes/profiles/<p>/config.yaml files, which are NOT in
# this repo. It is idempotent (re-running is a no-op once applied) and reversible
# (a timestamped .bak-skills-allowlist-* is written before any change; restore by
# copying it back). It does a comment-preserving ruamel.yaml round-trip so the
# rest of each config (security block, MCP notes, fallback docs) is untouched.
#
# It does NOT restart the gateway or delete the .skills_prompt_snapshot.json.
# Those are deliberate, separate live-service steps — see the printed reminder
# and docs/skills_allowlist.md. Rationale: the disk snapshot is keyed by the
# LOCAL skills_dir manifest only, so an external_dirs change won't auto-invalidate
# it, and the per-process external-dirs LRU cache only clears on restart.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PROFILES_DIR="$HERMES_HOME/profiles"
SS="$HERMES_HOME/shared-skills"

# Prefer the hermes venv python (has ruamel.yaml for comment-preserving edits).
PYBIN="$HERMES_HOME/hermes-agent/venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="$(command -v python3)"

if [ ! -d "$PROFILES_DIR" ]; then
  echo "error: $PROFILES_DIR not found — run on the Praetorium box" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"

# Role-scoped spec. external_dirs are shared-skills subdirs (walked recursively);
# disabled are LOCAL skill frontmatter names to hide from the index. Keep the
# role-critical skills each profile actually uses:
#   claudius (research analyst): plugin-qmd + vault-business + plugin-shared
#   augustus (content/vault ops): vault-business + plugin-shared
#   trajan   (executor engineer): plugin-official + plugin-shared + anthropic-generic
#   marcus   (orchestrator/gov):  plugin-shared + vault-business + plugin-official
SPEC_JSON="$(cat <<JSON
{
  "claudius": {
    "external_dirs": ["$SS/plugin-qmd", "$SS/vault-business", "$SS/plugin-shared"],
    "disabled": ["apple-notes","apple-reminders","findmy","imessage","computer-use","openhue","xurl","gif-search","heartmula","songsee","youtube-content","codebase-inspection","github-auth","github-code-review","github-issues","github-pr-workflow","github-repo-management","huggingface-hub","evaluating-llms-harness","weights-and-biases","llama-cpp","serving-llms-vllm","audiocraft-audio-generation","segment-anything-model","petdex","yuanbao","dogfood"]
  },
  "augustus": {
    "external_dirs": ["$SS/vault-business", "$SS/plugin-shared"],
    "disabled": ["apple-notes","apple-reminders","findmy","imessage","computer-use","openhue","xurl","huggingface-hub","evaluating-llms-harness","weights-and-biases","llama-cpp","serving-llms-vllm","audiocraft-audio-generation","segment-anything-model","gif-search","heartmula","songsee","petdex","yuanbao","dogfood"]
  },
  "trajan": {
    "external_dirs": ["$SS/plugin-official", "$SS/plugin-shared", "$SS/anthropic-generic"],
    "disabled": ["apple-notes","apple-reminders","findmy","imessage","openhue","xurl","gif-search","heartmula","songsee","youtube-content","huggingface-hub","evaluating-llms-harness","weights-and-biases","llama-cpp","serving-llms-vllm","audiocraft-audio-generation","segment-anything-model","petdex","yuanbao","dogfood"]
  },
  "marcus": {
    "external_dirs": ["$SS/plugin-shared", "$SS/vault-business", "$SS/plugin-official"],
    "disabled": ["apple-notes","apple-reminders","findmy","imessage","computer-use","openhue","xurl","gif-search","heartmula","songsee","youtube-content","huggingface-hub","evaluating-llms-harness","weights-and-biases","llama-cpp","serving-llms-vllm","audiocraft-audio-generation","segment-anything-model","petdex","yuanbao","dogfood"]
  }
}
JSON
)"

export SPEC_JSON PROFILES_DIR STAMP

"$PYBIN" - <<'PY'
import json, os, shutil, sys
from pathlib import Path

spec = json.loads(os.environ["SPEC_JSON"])
profiles_dir = Path(os.environ["PROFILES_DIR"])
stamp = os.environ["STAMP"]

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    have_ruamel = True
except Exception:
    import yaml as _pyyaml  # noqa: F401
    have_ruamel = False
    print("WARNING: ruamel.yaml unavailable — falling back to PyYAML, which "
          "DROPS COMMENTS. Aborting to avoid clobbering config comments.",
          file=sys.stderr)
    sys.exit(2)

def as_seq(items):
    seq = CommentedSeq(items)
    return seq

changed_any = False
for profile, cfg in spec.items():
    path = profiles_dir / profile / "config.yaml"
    if not path.is_file():
        print(f"skip {profile}: {path} not found")
        continue
    with path.open() as fh:
        doc = yaml.load(fh)
    if doc is None:
        print(f"skip {profile}: empty config")
        continue

    skills = doc.get("skills")
    if skills is None:
        from ruamel.yaml.comments import CommentedMap
        skills = CommentedMap()
        doc["skills"] = skills

    cur_ext = list(skills.get("external_dirs") or [])
    cur_dis = list(skills.get("disabled") or [])
    want_ext = list(cfg["external_dirs"])
    want_dis = list(cfg["disabled"])

    if cur_ext == want_ext and cur_dis == want_dis:
        print(f"unchanged {profile}: already at target external_dirs "
              f"({len(want_ext)}) + disabled ({len(want_dis)})")
        continue

    backup = path.with_name(f"config.yaml.bak-skills-allowlist-{stamp}")
    shutil.copy2(path, backup)
    skills["external_dirs"] = as_seq(want_ext)
    skills["disabled"] = as_seq(want_dis)
    with path.open("w") as fh:
        yaml.dump(doc, fh)
    changed_any = True
    print(f"updated {profile}: external_dirs {len(cur_ext)}->{len(want_ext)} "
          f"subdirs, disabled {len(cur_dis)}->{len(want_dis)} names "
          f"(backup: {backup.name})")

print()
if changed_any:
    print("Config edits applied. NEXT (separate live-service steps — NOT done here):")
    print("  1. Delete stale snapshots so the index rebuilds:")
    print("       rm -f ~/.hermes/profiles/{claudius,augustus,trajan,marcus}/.skills_prompt_snapshot.json")
    print("  2. Restart the gateway to clear the per-process external-dirs cache:")
    print("       XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user restart hermes-gateway")
    print("  Cron oneshots spawn fresh processes and pick up the change automatically.")
else:
    print("No changes needed — all profiles already at target.")
PY
