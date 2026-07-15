"""
OpenCode observability mitmproxy addon.

Captures LLM API request/response flows for analysis.
Based on the approach from:
    https://github.com/agardnerIT/opencode-video-content (Apache-2.0)

Differences from upstream:
    - Detects multiple request shapes (messages/input/prompt) not just 'messages'
    - Sanitizes host/path for safe filenames
    - Strips auth headers and cookies before capture
    - Records structured metadata (model, streaming, usage, timestamps)
    - Handles streaming responses and malformed JSON gracefully
    - Configurable output directory
    - UTC timestamps and collision-resistant filenames
    - Never writes to 0.0.0.0 (localhost only)
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone

from mitmproxy import http

# ── Configuration ──────────────────────────────────────────────────────────────

# Relative default when OPENCODE_OBSERVABILITY_DIR is unset.
DEFAULT_OUTPUT_DIR = os.path.join("var", "opencode-observability", "flows")

# Keys whose values are redacted in capture metadata (not in request bodies)
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "proxy-authorization",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

_sanitize_re = re.compile(r"[^a-zA-Z0-9._-]")


def sanitize_for_filename(value: str) -> str:
    return _sanitize_re.sub("_", value)[:80]


def redact_headers(headers: dict) -> dict:
    return {k: ("[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v)
            for k, v in headers.items()}


def is_llm_request(body: dict) -> bool:
    """Detect common LLM request shapes."""
    if not isinstance(body, dict):
        return False
    shapes = ("messages", "input", "prompt", "contents")
    return any(k in body for k in shapes)


def extract_model(body: dict) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("model", "model_id"):
        val = body.get(key)
        if val:
            return str(val)
    return None


def resolve_flows_dir(env_value: str | None = None) -> str:
    """Resolve capture directory from env or default.

    OPENCODE_OBSERVABILITY_DIR may be either:
      - a root dir (e.g. $PWD/var) → appends opencode-observability/flows
      - a flows dir ending in 'flows' → used as-is
    """
    root = env_value if env_value is not None else os.environ.get("OPENCODE_OBSERVABILITY_DIR")
    if not root:
        return DEFAULT_OUTPUT_DIR
    normalized = root.rstrip(os.sep)
    if normalized.endswith("flows"):
        return root
    return os.path.join(root, "opencode-observability", "flows")


def output_dir() -> str:
    return resolve_flows_dir()


def _ensure_output_dir() -> str:
    d = output_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


# ── Flow state tracking ───────────────────────────────────────────────────────

pending_requests: dict[str, dict] = {}
counter = 0


def request(flow: http.HTTPFlow) -> None:
    global counter

    try:
        body = json.loads(flow.request.get_text())
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        return

    if not is_llm_request(body):
        return

    host = flow.request.pretty_host
    path = flow.request.path
    method = flow.request.method
    timestamp = datetime.now(timezone.utc).isoformat()
    model = extract_model(body)
    streaming = body.get("stream", False)

    safe_host = sanitize_for_filename(host)
    safe_path = sanitize_for_filename(path.split("?")[0])
    counter += 1
    flow_id = str(uuid.uuid4())[:8]
    filename = f"{safe_host}_{safe_path}_{int(time.time())}_{counter:04d}_{flow_id}.json"

    filepath = os.path.join(_ensure_output_dir(), filename)
    os.makedirs(os.path.dirname(filepath) or ".", mode=0o700, exist_ok=True)

    record = {
        "_meta": {
            "timestamp": timestamp,
            "host": host,
            "path": path,
            "method": method,
            "model": model,
            "streaming": streaming,
            "filename": filename,
        },
        "request": {
            "headers": redact_headers(dict(flow.request.headers)),
            "body": body,
        },
    }

    pending_requests[flow_id] = {
        "filepath": filepath,
        "record": record,
        "start_time": time.time(),
    }

    # Write initial request capture
    with open(filepath, "w") as f:
        json.dump(record, f, indent=2, default=str)


def response(flow: http.HTTPFlow) -> None:
    if not flow.response:
        return

    # Match by host/path proximity as a fallback
    flow_id = None
    for fid, state in pending_requests.items():
        rec = state["record"]["_meta"]
        if rec["host"] == flow.request.pretty_host and rec["path"] == flow.request.path:
            flow_id = fid
            break

    if not flow_id:
        return

    state = pending_requests.pop(flow_id)
    filepath = state["filepath"]
    record = state["record"]
    latency = time.time() - state["start_time"]

    try:
        resp_body = flow.response.get_text()
        resp_json = json.loads(resp_body) if resp_body else {}
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        resp_json = resp_body if resp_body else {}

    usage = None
    if isinstance(resp_json, dict):
        usage = resp_json.get("usage")

    record["_meta"]["status_code"] = flow.response.status_code
    record["_meta"]["latency_seconds"] = round(latency, 3)
    record["_meta"]["usage_found"] = usage is not None
    record["response"] = {
        "headers": redact_headers(dict(flow.response.headers)),
        "status_code": flow.response.status_code,
        "body": resp_json,
        "usage": usage,
    }

    with open(filepath, "w") as f:
        json.dump(record, f, indent=2, default=str)


def error(flow: http.HTTPFlow) -> None:
    flow_id = None
    for fid, state in pending_requests.items():
        rec = state["record"]["_meta"]
        if rec["host"] == flow.request.pretty_host:
            flow_id = fid
            break

    if flow_id:
        state = pending_requests.pop(flow_id)
        state["record"]["_meta"]["error"] = str(flow.error) if flow.error else "unknown"
        with open(state["filepath"], "w") as f:
            json.dump(state["record"], f, indent=2, default=str)
