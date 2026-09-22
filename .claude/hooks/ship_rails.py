#!/usr/bin/env python3
"""PreToolUse hook: the ship RAILS (.claude/workflows/ship-dev-plan.js) as blocks, not prose.

It holds the rails for an agent that has not read the prompt, not against an adversary:
python3 -c and node -e bodies are not inspected. The edit rails (an existing test, a gate
script, this file) lift with SHIP_RAILS_OVERRIDE="<reason>" in the launching shell and
record one line in <git-common-dir>/ship_rails_overrides.log; the command rails never lift.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import subprocess
import sys

MARKER = os.path.join("bin", "verify.sh")
GATE_SCRIPTS = {"bin/verify.sh", "bin/check_deploy_drift.sh", ".claude/hooks/ship_rails.py"}
REFS = ("origin/main", "main", "HEAD")
EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}
PREFIX_WORDS = {"sudo", "command", "nice", "time", "env"}
SHELLS = {"bash", "sh", "zsh"}
ANY_ARG_WRITERS = {"tee", "truncate", "rm", "unlink", "shred", "mv"}
LAST_ARG_WRITERS = {"cp", "install", "rsync"}
GIT_WRITERS = {"rm", "mv", "checkout", "restore", "clean"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree"}
LIFECYCLE = {"start", "stop", "restart", "enable", "disable", "reenable", "try-restart",
             "reload-or-restart", "mask", "unmask", "kill"}
SEPARATOR = re.compile(r"^[;|&()]+$")
REDIRECT = re.compile(r"^&?>{1,2}\|?")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
IN_PLACE = re.compile(r"^(--in-place|-[A-Za-z]*i)")
ADD_ALL = re.compile(r"^-[A-Za-z]*A")
COMMIT_N = re.compile(r"^-[A-Za-z]*n[A-Za-z]*$")
DASH_C = re.compile(r"^-[A-Za-z]*c$")
PATHISH = re.compile(r"[A-Za-z0-9_~.]")
HELP = ('Rails: .claude/workflows/ship-dev-plan.js RAILS. Edit rails lift with '
        'SHIP_RAILS_OVERRIDE="<reason>" in the launching shell (recorded in '
        '.git/ship_rails_overrides.log); command rails do not.')


class Refused(Exception):
    def __init__(self, rail: str, target: object):
        super().__init__(rail)
        self.rail, self.target = rail, target


def read_hook_input() -> dict | None:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def repo_root(path: str) -> str | None:
    current = path
    while not os.path.isfile(os.path.join(current, MARKER)):
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return current


def protected_rel(path: str, cwd: str) -> tuple[str, str, str] | None:
    absolute = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    root = repo_root(absolute)
    if root is None:
        return None
    rel = os.path.relpath(absolute, root)
    if rel == "tests" or rel.startswith("tests/"):
        return root, rel, "edit-existing-test"
    if rel in GATE_SCRIPTS:
        return root, rel, "edit-gate-script"
    return None


def git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)


def existing_ref(root: str) -> str | None:
    for ref in REFS:
        code = git(root, "rev-parse", "--verify", "-q", ref).returncode
        if code == 0:
            return ref
        if code != 1:
            return None
    return None


def is_existing(root: str, rel: str) -> bool:
    ref = existing_ref(root)
    if ref is None:
        return True
    return git(root, "rev-parse", "--verify", "-q", f"{ref}:{rel}").returncode != 1


def tokenize(cmd: str) -> list[str]:
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return cmd.split()


def segments(tokens: list[str]) -> list[list[str]]:
    result: list[list[str]] = [[]]
    for token in tokens:
        if SEPARATOR.match(token):
            result.append([])
        else:
            result[-1].append(token)
    return [seg for seg in result if seg]


def command_index(seg: list[str]) -> int:
    for index, token in enumerate(seg):
        if token not in PREFIX_WORDS and not ASSIGNMENT.match(token):
            return index
    return len(seg)


def command_word(seg: list[str]) -> str:
    index = command_index(seg)
    return os.path.basename(seg[index]) if index < len(seg) else ""


def args(seg: list[str]) -> list[str]:
    result, skip = [], False
    for token in seg[command_index(seg) + 1:]:
        match = REDIRECT.match(token)
        if skip or match:
            skip = bool(match) and not token[match.end():]
            continue
        result.append(token)
    return result


def redirect_targets(seg: list[str]) -> list[str]:
    targets = []
    for index, token in enumerate(seg):
        match = REDIRECT.match(token)
        if not match or token[match.end():].startswith("&"):
            continue
        rest = token[match.end():]
        targets.append(rest or (seg[index + 1] if index + 1 < len(seg) else ""))
    return targets


def is_path_token(token: str) -> bool:
    return not token.startswith("-") and "://" not in token and bool(PATHISH.search(token))


def git_subcommand(seg: list[str]) -> str | None:
    skip = False
    for token in seg[command_index(seg) + 1:]:
        if skip:
            skip = False
        elif token in GIT_VALUE_OPTIONS:
            skip = True
        elif not token.startswith("-"):
            return token
    return None


def written_args(seg: list[str]) -> list[str]:
    word, positional = command_word(seg), [arg for arg in args(seg) if is_path_token(arg)]
    if word in {"sed", "perl"} and any(IN_PLACE.match(arg) for arg in args(seg)):
        return positional
    if word in ANY_ARG_WRITERS or (word == "git" and git_subcommand(seg) in GIT_WRITERS):
        return positional
    if word in LAST_ARG_WRITERS:
        return positional[-1:]
    return []


def write_targets(seg: list[str], cwd: str) -> list[tuple[str, str, str]]:
    candidates = redirect_targets(seg) + written_args(seg)
    protected = (protected_rel(candidate, cwd) for candidate in candidates if candidate)
    return [target for target in protected if target]


def nested_command(seg: list[str]) -> str | None:
    word, rest = command_word(seg), args(seg)
    if word == "eval":
        return " ".join(rest)
    if word in SHELLS:
        for index, token in enumerate(rest[:-1]):
            if DASH_C.match(token):
                return rest[index + 1]
    return None


def all_segments(cmd: str, depth: int = 0) -> list[list[str]]:
    result = []
    for seg in segments(tokenize(cmd)):
        result.append(seg)
        nested = nested_command(seg)
        if nested is not None and depth < 3:
            result += all_segments(nested, depth + 1)
    return result


def check_no_verify(seg: list[str]) -> None:
    if any(token == "--no-verify" or token.startswith("--no-verify=") for token in seg):
        raise Refused("no-verify", seg)
    if command_word(seg) == "git" and git_subcommand(seg) == "commit":
        if any(COMMIT_N.match(arg) for arg in args(seg)):
            raise Refused("no-verify", seg)


def check_git_add_all(seg: list[str]) -> None:
    if command_word(seg) != "git" or git_subcommand(seg) != "add":
        return
    for arg in args(seg):
        if arg in {"--all", "--no-ignore-removal"} or ADD_ALL.match(arg):
            raise Refused("git-add-all", seg)


def check_deploy_prune(seg: list[str]) -> None:
    if command_word(seg) == "deploy" and "--prune" in seg and "--dry-run" not in seg:
        raise Refused("deploy-prune", seg)


def check_systemctl_lifecycle(seg: list[str]) -> None:
    if command_word(seg) == "systemctl" and LIFECYCLE.intersection(args(seg)):
        raise Refused("systemctl-lifecycle", seg)


COMMAND_RAILS = (check_no_verify, check_git_add_all, check_deploy_prune, check_systemctl_lifecycle)


def override_reason() -> str:
    return os.environ.get("SHIP_RAILS_OVERRIDE", "").strip()


def overrides_log(root: str) -> str:
    done = git(root, "rev-parse", "--git-common-dir")
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or "git common dir unavailable")
    return os.path.join(root, done.stdout.strip(), "ship_rails_overrides.log")


def record_override(tool: str, root: str, rel: str, rail: str, reason: str) -> None:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(overrides_log(root), "a", encoding="utf-8") as log:
        log.write(f"{stamp}\t{tool}\t{rail}\t{rel}\t{reason}\n")


def lift_or_refuse(tool: str, root: str, rel: str, rail: str) -> None:
    reason = override_reason()
    if not reason:
        raise Refused(rail, rel)
    try:
        record_override(tool, root, rel, rail, reason)
    except OSError as exc:
        raise Refused(rail, f"{rel} (override not recorded: {exc})") from exc


def check_bash(cmd: str, cwd: str, tool: str) -> None:
    segs = all_segments(cmd)
    for seg in segs:
        for rail in COMMAND_RAILS:
            rail(seg)
    for seg in segs:
        for root, rel, rail_name in write_targets(seg, cwd):
            if is_existing(root, rel):
                lift_or_refuse(tool, root, rel, rail_name)


def check_edit(path: str, cwd: str, tool: str) -> None:
    protected = protected_rel(path, cwd)
    if protected and is_existing(protected[0], protected[1]):
        lift_or_refuse(tool, *protected)


def refuse(rail: str, target: object) -> int:
    excerpt = " ".join(target) if isinstance(target, list) else str(target)
    excerpt = " ".join(excerpt.split())[:80]
    sys.stderr.write(f"ship-rails: refused {rail} — {excerpt}. {HELP}\n")
    return 2


def main() -> int:
    data = read_hook_input()
    tool, tool_input = (data or {}).get("tool_name"), (data or {}).get("tool_input")
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return 0
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    try:
        if tool == "Bash" and isinstance(tool_input.get("command"), str):
            check_bash(tool_input["command"], cwd, tool)
        elif tool in EDIT_TOOLS and isinstance(tool_input.get("file_path"), str):
            check_edit(tool_input["file_path"], cwd, tool)
    except Refused as refusal:
        return refuse(refusal.rail, refusal.target)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — loud beats a rail that silently stopped holding
        sys.stderr.write(f"ship-rails: internal error — {exc}\n")
        sys.exit(2)
