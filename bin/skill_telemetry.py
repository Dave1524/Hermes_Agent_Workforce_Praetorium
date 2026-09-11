#!/usr/bin/env python3
"""Which pointer skills one headless run was offered, invoked and read (T3.3).

Usage: skill_telemetry.py <transcript.jsonl> [--namespace praetorium-]

Reads a Claude Code session transcript — nothing else on the filesystem — and prints one line:

    offered=<csv|none> invoked=<csv|none> read=<csv|none>

Each csv is the sorted, unique, unqualified pointer names (`meeting-prep`, never
`praetorium-claudius:meeting-prep`), comma-joined with no spaces, so agent_propose.sh can append
the values to cost.log and scorecard.sh can tokenise them on whitespace.

  offered  every `attachment.type == "skill_listing"` record's `names[]` inside the namespace
  invoked  every assistant `tool_use` named `Skill` whose `input.skill` is inside the namespace
  read     every assistant `tool_use` named `Read` whose `input.file_path` is a SKILL.md — the
           canonical vault file or the pointer file itself

This is a parser, not a grep: the Skill tool's own schema is snapshotted into every transcript
as the string `"name":"Skill"`, and only a `tool_use` content block is an invocation.

Exit 2: the transcript does not exist. Exit 1: anything else. Blank or unparseable lines skip.
"""
import json
import re
import sys

DEFAULT_NAMESPACE = "praetorium-"
SKILL_MD_PATHS = (
    re.compile(r"/08_skills/([^/]+)/SKILL\.md$"),
    re.compile(r"/skills/[^/]+/skills/([^/]+)/SKILL\.md$"),
)


def parse_args(argv):
    args = list(argv)
    namespace = DEFAULT_NAMESPACE
    if "--namespace" in args:
        i = args.index("--namespace")
        namespace = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        raise SystemExit("usage: skill_telemetry.py <transcript.jsonl> [--namespace praetorium-]")
    return args[0], re.compile("^" + re.escape(namespace) + r"[^:]*:(.+)$")


def records(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def listing_names(record):
    attachment = record.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "skill_listing":
        return []
    names = attachment.get("names")
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def tool_uses(record):
    if record.get("type") != "assistant":
        return
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            yield block.get("name"), block["input"]


def skill_from_path(file_path):
    for pattern in SKILL_MD_PATHS:
        match = pattern.search(file_path)
        if match:
            return match.group(1)
    return None


def unqualified(name, namespace_re):
    match = namespace_re.match(name)
    return match.group(1) if match else None


def collect(path, namespace_re):
    offered, invoked, read = set(), set(), set()
    for record in records(path):
        if not isinstance(record, dict):
            continue
        offered.update(filter(None, (unqualified(n, namespace_re) for n in listing_names(record))))
        for name, tool_input in tool_uses(record):
            if name == "Skill" and isinstance(tool_input.get("skill"), str):
                invoked.add(unqualified(tool_input["skill"], namespace_re))
            elif name == "Read" and isinstance(tool_input.get("file_path"), str):
                read.add(skill_from_path(tool_input["file_path"]))
    return offered, invoked - {None}, read - {None}


def csv(names):
    return ",".join(sorted(names)) if names else "none"


def main(argv):
    path, namespace_re = parse_args(argv)
    try:
        offered, invoked, read = collect(path, namespace_re)
    except FileNotFoundError:
        print(f"skill_telemetry: no transcript at {path}", file=sys.stderr)
        return 2
    print(f"offered={csv(offered)} invoked={csv(invoked)} read={csv(read)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # fail loud, never half a line
        print(f"skill_telemetry: {exc}", file=sys.stderr)
        sys.exit(1)
