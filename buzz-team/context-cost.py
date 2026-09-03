#!/usr/bin/env python3
"""Per-turn prompt cost for the Buzz fleet, split by prompt layer and by channel.

Answers one question: is channel membership inflating what we pay per turn?

buzz-acp assembles every prompt from labelled blocks — [Base], [System],
[Team Instructions], [Agent Memory — core], [Context], [Buzz event: ...]. Only
[Context] grows with channel traffic; the rest are fixed per agent. Reporting a
single total hides which one moved, so each is measured separately.

The agents run with cwd /home/dave, so their Claude Code transcripts land in the
same directory as Dave's own interactive sessions. A session is a fleet session
iff its first user message carries a [Base] block — that marker is written by
buzz-acp and by nothing else.

Augustus is on the Codex harness and writes no transcript here; his rollouts live
under CODEX_HOME. He is reported as absent rather than silently omitted, because a
missing agent and a quiet agent look identical in a per-agent table.
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TRANSCRIPTS = Path.home() / ".claude/projects/-home-dave"
AGENTS = ("marcus", "claudius", "trajan", "augustus")
LAYERS = ("[Base]", "[System]", "[Team Instructions]", "[Agent Memory — core]", "[Context]")
CHANNEL_RE = re.compile(r"^Channel:\s*(.+?)\s*\(#([0-9a-f-]+)\)", re.M)


def text_blocks(record):
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]


def layer_of(block):
    for layer in LAYERS:
        if block.startswith(layer):
            return layer
    return None


def agent_of(system_block):
    match = re.search(r"You are (\w+)", system_block)
    return match.group(1).lower() if match else None


def channel_of(context_block):
    match = CHANNEL_RE.search(context_block)
    return (match.group(1), match.group(2)[:8]) if match else ("(direct message)", "")


def billed_tokens(record):
    usage = (record.get("message") or {}).get("usage") or {}
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def read_turn(path):
    """First fleet-assembled prompt in a transcript, plus that session's billed input."""
    layers, requests, tokens, stamp = {}, 0, 0, None
    with path.open() as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "user" and not layers:
                for block in text_blocks(record):
                    layer = layer_of(block)
                    if layer:
                        layers[layer] = block
                if layers:
                    stamp = record.get("timestamp")
            elif record.get("type") == "assistant":
                billed = billed_tokens(record)
                if billed:
                    requests += 1
                    tokens += billed
    return layers, requests, tokens, stamp


def collect(since):
    turns = []
    for path in TRANSCRIPTS.glob("*.jsonl"):
        layers, requests, tokens, stamp = read_turn(path)
        if "[Base]" not in layers:
            continue
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
        if since and when and when < since:
            continue
        name, uuid = channel_of(layers.get("[Context]", ""))
        turns.append(
            {
                "agent": agent_of(layers.get("[System]", "")) or "(unknown)",
                "channel": name,
                "uuid": uuid,
                "sizes": {layer: len(layers.get(layer, "")) for layer in LAYERS},
                "requests": requests,
                "tokens": tokens,
                "when": when,
            }
        )
    return turns


def report(turns, since_label):
    if not turns:
        print(f"No fleet turns found ({since_label}).")
        return

    print(f"Fleet prompt cost — {len(turns)} turns, {since_label}\n")

    print("Static layers, per agent (bytes; resent on EVERY request of a turn)")
    print(f"  {'agent':<10} {'turns':>5} {'[Base]':>8} {'[System]':>9} {'[Team]':>8} {'[Memory]':>9} {'static':>8}")
    by_agent = defaultdict(list)
    for turn in turns:
        by_agent[turn["agent"]].append(turn)
    for agent in sorted(by_agent):
        rows = by_agent[agent]
        newest = max(rows, key=lambda r: r["when"] or datetime.min.replace(tzinfo=timezone.utc))
        sizes = newest["sizes"]
        static = sum(sizes[l] for l in LAYERS if l != "[Context]")
        print(
            f"  {agent:<10} {len(rows):>5} {sizes['[Base]']:>8} {sizes['[System]']:>9} "
            f"{sizes['[Team Instructions]']:>8} {sizes['[Agent Memory — core]']:>9} {static:>8}"
        )
    for missing in (a for a in AGENTS if a not in by_agent):
        note = " (Codex harness — rollouts under CODEX_HOME, not measured here)" if missing == "augustus" else ""
        print(f"  {missing:<10} {'-':>5}   no transcript{note}")

    print("\n[Context] scrollback, per channel — the only layer channel traffic moves")
    print(f"  {'channel':<28} {'agent':<10} {'turns':>5} {'mean B':>8} {'max B':>8} {'% of prompt':>12}")
    by_channel = defaultdict(list)
    for turn in turns:
        by_channel[(turn["channel"], turn["uuid"], turn["agent"])].append(turn)
    for (name, uuid, agent), rows in sorted(by_channel.items(), key=lambda kv: -max(r["sizes"]["[Context]"] for r in kv[1])):
        ctx = [r["sizes"]["[Context]"] for r in rows]
        total = max(sum(r["sizes"].values()) for r in rows) or 1
        label = f"{name} #{uuid}" if uuid else name
        print(
            f"  {label:<28.28} {agent:<10} {len(rows):>5} {sum(ctx)//len(ctx):>8} {max(ctx):>8} "
            f"{max(ctx) * 100 / total:>11.1f}%"
        )

    billed = [t for t in turns if t["requests"]]
    if billed:
        print("\nBilled input per turn (input + cache_creation + cache_read, all requests)")
        print(f"  {'agent':<10} {'turns':>5} {'reqs/turn':>10} {'mean tok':>10} {'max tok':>10}")
        for agent in sorted({t["agent"] for t in billed}):
            rows = [t for t in billed if t["agent"] == agent]
            toks = [t["tokens"] for t in rows]
            reqs = sum(t["requests"] for t in rows) / len(rows)
            print(f"  {agent:<10} {len(rows):>5} {reqs:>10.1f} {sum(toks)//len(toks):>10} {max(toks):>10}")


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    label = f"last {days}d" if days else "all time"
    report(collect(since), label)


if __name__ == "__main__":
    main()
