#!/usr/bin/env python3
"""
Analyze captured OpenCode LLM flows and produce a compact report.

Usage:
    python3 analyze_flows.py [--prompts] [--json] [flows_dir]

If no flows_dir is given, reads from OPENCODE_OBSERVABILITY_DIR or
defaults to var/opencode-observability/flows/ relative to the repo root.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ── Token estimation ──────────────────────────────────────────────────────────
#
# These are rough approximations based on character-to-token ratios.
# OpenAI-compatible APIs typically use ~4 chars/token for English text.
# We label all estimates clearly when the provider does not return usage metadata.

CHARS_PER_TOKEN = 4.0
TOKEN_ESTIMATE_DISCLAIMER = "ESTIMATED (character-based)"

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) // CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: list) -> dict:
    """Return per-role token estimates."""
    role_counts: dict[str, int] = defaultdict(int)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(str(c) for c in content)
        else:
            text = str(content)
        role_counts[msg.get("role", "unknown")] += estimate_tokens(text)
    return dict(role_counts)


def estimate_tool_definitions(body: dict) -> dict:
    tools = body.get("tools", body.get("functions", []))
    if not tools:
        return {"count": 0, "estimated_tokens": 0}
    total_chars = sum(len(json.dumps(t, default=str)) for t in tools)
    return {
        "count": len(tools),
        "estimated_tokens": estimate_tokens(json.dumps(tools, default=str)),
        "estimated_chars": total_chars,
    }


def is_title_generation(body: dict, meta: dict | None = None) -> bool:
    """Heuristic for title-generation / lightweight session-label calls."""
    meta = meta or {}
    model = str(meta.get("model") or body.get("model") or "").lower()
    path = str(meta.get("path") or "").lower()
    if "title" in path or model.endswith("-nano") or "gpt-5.4-nano" in model:
        return True

    messages = body.get("messages", body.get("input", []))
    if not isinstance(messages, list) or len(messages) != 1:
        return False
    msg = messages[0]
    if isinstance(msg, dict):
        content = msg.get("content", "")
        role = msg.get("role", "")
    else:
        content = str(msg)
        role = ""
    if isinstance(content, list):
        content = " ".join(str(c) for c in content)
    if not isinstance(content, str):
        return False
    # Short single-turn user/system prompts without tools look like title gen.
    if body.get("tools") or body.get("functions"):
        return False
    return len(content) < 200 and role in ("user", "system", "")


def extract_system_prompt(body: dict) -> tuple[str | None, int]:
    messages = body.get("messages", body.get("input", []))
    if not isinstance(messages, list):
        return None, 0
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, list):
                text = " ".join(str(c) for c in content)
            else:
                text = str(content)
            return text, estimate_tokens(text)
    return None, 0


def get_message_roles(body: dict) -> list[dict]:
    messages = body.get("messages", body.get("input", []))
    if isinstance(messages, list):
        out = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                text = " ".join(str(c) for c in content)
            else:
                text = str(content)
            out.append({
                "role": m.get("role", "unknown"),
                "content_chars": len(text),
                "estimated_tokens": estimate_tokens(text),
            })
        return out
    return []


# ── Analysis ───────────────────────────────────────────────────────────────────

def analyze_flows(flows_dir: str, show_prompts: bool = False, json_output: bool = False) -> dict:
    path = Path(flows_dir)
    if not path.is_dir():
        print(f"ERROR: flows directory not found: {flows_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(path.glob("*.json"))
    if not files:
        msg = f"No flow files found in {flows_dir}"
        if not json_output:
            print(msg)
        return {"flows_analyzed": 0}

    total_calls = 0
    model_counter: Counter = Counter()
    host_counter: Counter = Counter()
    title_gen_count = 0
    errors = []
    incomplete = []
    total_latency = 0.0
    latency_count = 0
    repeated_prompts: dict[str, int] = defaultdict(int)

    # Usage tracking
    actual_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    estimated_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    has_any_actual = False

    # Per-role token estimates
    role_tokens: Counter = Counter()

    # System prompt tracking
    system_prompt_sizes: list[int] = []
    first_system_prompt: str | None = None
    first_system_tokens = 0

    # Tool definitions
    tool_def_sizes: list[dict] = []

    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            incomplete.append(str(f))
            continue

        meta = data.get("_meta", {})
        req = data.get("request", {})
        resp = data.get("response")

        total_calls += 1
        host_counter[meta.get("host", "unknown")] += 1
        model = meta.get("model") or req.get("body", {}).get("model", "unknown")
        model_counter[model] += 1

        body = req.get("body", {})

        # Title generation detection
        if is_title_generation(body, meta):
            title_gen_count += 1

        # System prompt tracking
        sys_text, sys_tokens = extract_system_prompt(body)
        if sys_text is not None:
            system_prompt_sizes.append(sys_tokens)
            if first_system_prompt is None:
                first_system_prompt = sys_text[:200]
                first_system_tokens = sys_tokens

        # Role analysis
        roles = get_message_roles(body)
        for r in roles:
            role_tokens[r["role"]] += r.get("estimated_tokens", 0)

        # Tool definitions
        td = estimate_tool_definitions(body)
        if td["count"] > 0:
            tool_def_sizes.append(td)

        # Prompt repetition detection
        prompt_text = json.dumps(body.get("messages", body.get("input", "")), default=str)
        prompt_hash = prompt_text[:500]  # use prefix as approximate key
        repeated_prompts[prompt_hash] += 1

        # Usage metadata
        resp_body = resp.get("body", {}) if resp else {}
        usage = None
        if isinstance(resp_body, dict):
            usage = resp_body.get("usage")
        if not usage and resp:
            usage = resp.get("usage")

        if usage and isinstance(usage, dict):
            inp = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            if inp or out:
                has_any_actual = True
                actual_usage["input_tokens"] += inp
                actual_usage["output_tokens"] += out
                actual_usage["total_tokens"] += inp + out
            else:
                # Estimate from body size
                est = estimate_tokens(prompt_text)
                estimated_usage["input_tokens"] += est
                estimated_usage["output_tokens"] += estimate_tokens(
                    json.dumps(resp_body, default=str)
                )
                estimated_usage["total_tokens"] += est + estimate_tokens(
                    json.dumps(resp_body, default=str)
                )
        else:
            # No usage at all — estimate
            est = estimate_tokens(prompt_text)
            estimated_usage["input_tokens"] += est
            if resp:
                est_out = estimate_tokens(json.dumps(resp_body, default=str))
                estimated_usage["output_tokens"] += est_out
                estimated_usage["total_tokens"] += est + est_out
            else:
                estimated_usage["total_tokens"] += est

        # Latency
        lat = meta.get("latency_seconds")
        if lat is not None:
            total_latency += lat
            latency_count += 1

        # Error tracking
        if meta.get("error"):
            errors.append({
                "file": str(f),
                "error": meta["error"],
                "host": meta.get("host"),
            })

        # Incomplete (no response)
        if resp is None:
            incomplete.append(str(f))

        # Show prompts if requested
        if show_prompts and first_system_prompt is not None:
            pass  # handled below

    # Compute repetition stats
    unique_prompts = len(repeated_prompts)
    repeated_count = sum(1 for v in repeated_prompts.values() if v > 1)

    report = {
        "flows_analyzed": total_calls,
        "unique_models": dict(model_counter.most_common()),
        "hosts": dict(host_counter.most_common()),
        "title_generation_calls": title_gen_count,
        "usage": {
            "has_actual_metadata": has_any_actual,
            "actual": actual_usage if has_any_actual else None,
            "estimated": estimated_usage,
            "note": (f"Usage numbers are actual provider metadata."
                     if has_any_actual
                     else f"{TOKEN_ESTIMATE_DISCLAIMER}: {CHARS_PER_TOKEN} chars/token"),
        },
        "system_prompt": {
            "count_analyzed": len(system_prompt_sizes),
            "first_size_tokens": first_system_tokens,
            "first_size_chars": len(first_system_prompt) if first_system_prompt else 0,
        },
        "tool_definitions": {
            "calls_with_tools": len(tool_def_sizes),
            "total_tool_count": sum(t["count"] for t in tool_def_sizes),
            "estimated_total_tokens": sum(t["estimated_tokens"] for t in tool_def_sizes),
        },
        "role_token_estimates": dict(role_tokens),
        "latency": {
            "calls_with_latency": latency_count,
            "total_seconds": round(total_latency, 3),
            "average_seconds": round(total_latency / latency_count, 3) if latency_count else None,
        },
        "repeated_prompts": {
            "unique_prefixes": unique_prompts,
            "repeated_at_least_once": repeated_count,
        },
        "errors": errors,
        "incomplete_captures": incomplete,
    }

    return report


def print_report(report: dict, show_prompts: bool = False):
    print("=" * 60)
    print("  OpenCode Observability — Flow Analysis Report")
    print("=" * 60)

    if report.get("flows_analyzed") == 0:
        print("  No flows to analyze.")
        return

    print(f"\n  LLM calls analyzed:    {report['flows_analyzed']}")
    print(f"  Title-generation calls: {report['title_generation_calls']}")

    print(f"\n  ── Models ──")
    for model, count in report["unique_models"].items():
        print(f"    {model}: {count} call(s)")

    print(f"\n  ── Hosts ──")
    for host, count in report["hosts"].items():
        print(f"    {host}: {count} call(s)")

    # Usage
    usage = report["usage"]
    print(f"\n  ── Usage ──")
    if usage["has_actual_metadata"] and usage["actual"]:
        a = usage["actual"]
        print(f"    Input tokens:  {a['input_tokens']}  (actual provider metadata)")
        print(f"    Output tokens: {a['output_tokens']}  (actual provider metadata)")
        print(f"    Total tokens:  {a['total_tokens']}  (actual provider metadata)")
    if usage["estimated"]:
        e = usage["estimated"]
        label = "estimate" if not usage["has_actual_metadata"] else "unmetered (est.)"
        print(f"    Input tokens:  {e['input_tokens']}  ({label})")
        print(f"    Output tokens: {e['output_tokens']}  ({label})")
        print(f"    Total tokens:  {e['total_tokens']}  ({label})")
    print(f"    Note: {usage['note']}")

    # System prompt
    sp = report["system_prompt"]
    print(f"\n  ── System Prompt ──")
    print(f"    Calls with system prompt: {sp['count_analyzed']}")
    print(f"    First system-prompt size: {sp['first_size_tokens']} tokens (est.)")

    # Tool definitions
    td = report["tool_definitions"]
    print(f"\n  ── Tool Definitions ──")
    print(f"    Calls with tools:      {td['calls_with_tools']}")
    print(f"    Total tool count:      {td['total_tool_count']}")
    print(f"    Estimated token cost:  {td['estimated_total_tokens']}")

    # Per-role
    print(f"\n  ── Per-Role Token Estimates ──")
    for role, tokens in sorted(report["role_token_estimates"].items()):
        print(f"    {role}: ~{tokens} tokens")

    # Latency
    lat = report["latency"]
    print(f"\n  ── Latency ──")
    if lat["average_seconds"] is not None:
        print(f"    Total:   {lat['total_seconds']}s")
        print(f"    Average: {lat['average_seconds']}s across {lat['calls_with_latency']} calls")
    else:
        print(f"    No latency data captured")

    # Repetition
    rp = report["repeated_prompts"]
    print(f"\n  ── Prompt Repetition ──")
    if rp["unique_prefixes"] > 0:
        repeated = rp["repeated_at_least_once"]
        total = report["flows_analyzed"]
        unique = rp["unique_prefixes"]
        print(f"    {unique} unique prompt shapes across {total} calls")
        print(f"    {repeated} prompt(s) repeated across multiple calls")

    # Errors
    if report["errors"]:
        print(f"\n  ── Errors ({len(report['errors'])}) ──")
        for err in report["errors"]:
            print(f"    {err['file']}: {err['error']}")

    if report["incomplete_captures"]:
        print(f"\n  ── Incomplete Captures ({len(report['incomplete_captures'])}) ──")
        for f in report["incomplete_captures"]:
            print(f"    {f}")

    if show_prompts:
        print(f"\n  ── Prompts (first system prompt snippet) ──")
        print(f"    {report['system_prompt'].get('first_size_chars', 0)} chars")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze captured OpenCode LLM flows"
    )
    parser.add_argument(
        "flows_dir",
        nargs="?",
        default=None,
        help="Directory with captured flow JSON files "
             "(default: $OPENCODE_OBSERVABILITY_DIR or var/opencode-observability/flows/)",
    )
    parser.add_argument(
        "--prompts",
        action="store_true",
        help="Show system prompt contents (off by default)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON only",
    )
    args = parser.parse_args()

    if args.flows_dir:
        flows_dir = args.flows_dir
    elif os.environ.get("OPENCODE_OBSERVABILITY_DIR"):
        root = os.environ["OPENCODE_OBSERVABILITY_DIR"]
        normalized = root.rstrip(os.sep)
        if normalized.endswith("flows"):
            flows_dir = root
        else:
            flows_dir = os.path.join(root, "opencode-observability", "flows")
    else:
        # Default relative to repo root
        repo_root = Path(__file__).resolve().parent.parent.parent
        flows_dir = str(repo_root / "var" / "opencode-observability" / "flows")

    report = analyze_flows(flows_dir, show_prompts=args.prompts, json_output=args.json)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report, show_prompts=args.prompts)

    return 0 if report.get("flows_analyzed", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
