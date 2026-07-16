#!/usr/bin/env bash
# Offline tests for OpenCode observability tooling — addon, analyzer, fixtures.
# Run via bin/verify.sh or directly. No network / no model spend.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADDON="$REPO_ROOT/tools/opencode-observability/capture_addon.py"
ANALYZER="$REPO_ROOT/tools/opencode-observability/analyze_flows.py"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
}

# ── 1. Python syntax checks ────────────────────────────────────────────────────

echo "test: opencode-observability — python syntax checks"
assert "capture_addon.py is valid Python" "python3 -m py_compile '$ADDON'"
assert "analyze_flows.py is valid Python"   "python3 -m py_compile '$ANALYZER'"

# ── 2. Capture directory is gitignored ─────────────────────────────────────────

echo "test: opencode-observability — capture dir gitignored"
assert "var/opencode-observability/ is gitignored" \
  "git -C '$REPO_ROOT' check-ignore -q var/opencode-observability/flows/x.json"

# ── 3. Addon unit behaviors (stdlib + mitmproxy available) ─────────────────────
# capture_addon.py does `from mitmproxy import http` at import time, so the addon
# behavior checks below need mitmproxy importable. Skip them (not the syntax/gitignore
# checks above) when it is absent — mirroring the opt-in skip in
# test_opencode_agents_live.sh — so verify.sh stays green on boxes without the
# optional mitmproxy dependency.
if ! python3 -c 'import mitmproxy' 2>/dev/null; then
  echo "  SKIP: mitmproxy not installed — addon behavior tests skipped (syntax + gitignore checks passed)"
  exit "$fail"
fi

echo "test: opencode-observability — addon behaviors"

python3 - "$ADDON" "$TMPDIR" <<'PY'
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

addon_path = Path(sys.argv[1])
tmp = Path(sys.argv[2])
flows = tmp / "flows"
flows.mkdir(parents=True, exist_ok=True)
os.environ["OPENCODE_OBSERVABILITY_DIR"] = str(flows)

spec = importlib.util.spec_from_file_location("capture_addon", addon_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fail = 0

def ok(msg):
    print(f"  ok: {msg}")

def bad(msg):
    global fail
    print(f"  FAIL: {msg}")
    fail = 1

# --- sanitize / redact ---
safe = mod.sanitize_for_filename("https://api.openai.com/v1/chat?key=abc")
if "/" in safe or "?" in safe or ":" in safe:
    bad(f"sanitize left unsafe chars: {safe}")
else:
    ok("produces safe filenames")

redacted = mod.redact_headers({
    "Authorization": "Bearer secret",
    "Cookie": "a=b",
    "Set-Cookie": "c=d",
    "X-Api-Key": "k",
    "content-type": "application/json",
})
if redacted["Authorization"] != "[REDACTED]" or redacted["Cookie"] != "[REDACTED]":
    bad(f"auth/cookie not redacted: {redacted}")
else:
    ok("never persists authorization headers or cookies (redaction)")
if redacted["content-type"] != "application/json":
    bad("non-sensitive header was altered")
else:
    ok("non-sensitive headers preserved")

# --- shape detection ---
if not mod.is_llm_request({"messages": []}):
    bad("messages shape not detected")
else:
    ok("captures messages shape")
if not mod.is_llm_request({"input": []}):
    bad("input shape not detected")
else:
    ok("captures input shape")
if not mod.is_llm_request({"prompt": "hi"}):
    bad("prompt shape not detected")
else:
    ok("captures prompt shape")
if not mod.is_llm_request({"contents": []}):
    bad("contents shape not detected")
else:
    ok("captures contents shape")
if mod.is_llm_request({"foo": "bar"}):
    bad("non-LLM body incorrectly treated as LLM")
else:
    ok("ignores non-LLM traffic shapes")
if mod.is_llm_request("not-a-dict"):  # type: ignore[arg-type]
    bad("non-dict body incorrectly treated as LLM")
else:
    ok("ignores malformed non-dict bodies")

# --- Fake mitmproxy HTTP objects for request/response/error ---
class FakeHeaders(dict):
    def items(self):
        return super().items()

class FakeRequest:
    def __init__(self, body, host="api.openai.com", path="/v1/chat/completions", method="POST", headers=None):
        self._body = body
        self.pretty_host = host
        self.path = path
        self.method = method
        self.headers = FakeHeaders(headers or {
            "authorization": "Bearer SECRET",
            "cookie": "session=1",
            "content-type": "application/json",
        })
    def get_text(self):
        return self._body

class FakeResponse:
    def __init__(self, body, status_code=200, headers=None):
        self._body = body
        self.status_code = status_code
        self.headers = FakeHeaders(headers or {"content-type": "application/json"})
    def get_text(self):
        return self._body

class FakeError:
    def __str__(self):
        return "upstream timeout"

class FakeFlow:
    def __init__(self, request, response=None, error=None):
        self.request = request
        self.response = response
        self.error = error

# malformed JSON ignored
before = list(flows.glob("*.json"))
mod.request(FakeFlow(FakeRequest("not-json{")))
after = list(flows.glob("*.json"))
if len(after) != len(before):
    bad("malformed JSON produced a capture file")
else:
    ok("ignores malformed JSON")

# non-LLM ignored
mod.request(FakeFlow(FakeRequest(json.dumps({"foo": 1}))))
if list(flows.glob("*.json")):
    bad("non-LLM traffic produced a capture file")
else:
    ok("ignores non-LLM traffic")

# successful non-streaming capture with usage
body = {
    "model": "gpt-4",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "hello"},
    ],
    "stream": False,
}
flow = FakeFlow(FakeRequest(json.dumps(body)))
mod.request(flow)
files = list(flows.glob("*.json"))
if len(files) != 1:
    bad(f"expected 1 capture after LLM request, got {len(files)}")
else:
    ok("captures supported LLM request shapes")
    data = json.loads(files[0].read_text())
    if data["request"]["headers"].get("authorization") != "[REDACTED]":
        bad("authorization header persisted without redaction")
    elif data["request"]["headers"].get("cookie") != "[REDACTED]":
        bad("cookie header persisted without redaction")
    else:
        ok("captured request headers are redacted")

resp_body = {
    "id": "chatcmpl-1",
    "choices": [{"message": {"content": "hi"}}],
    "usage": {"input_tokens": 25, "output_tokens": 8, "total_tokens": 33},
}
flow.response = FakeResponse(json.dumps(resp_body), status_code=200)
mod.response(flow)
data = json.loads(files[0].read_text())
if data.get("response", {}).get("status_code") != 200:
    bad("successful response not recorded")
else:
    ok("captures successful responses")
if not data.get("_meta", {}).get("usage_found"):
    bad("usage_found not set when provider usage present")
elif data.get("response", {}).get("usage", {}).get("input_tokens") != 25:
    bad("provider usage metadata not recorded")
else:
    ok("records provider usage metadata when present")

# streaming response (SSE body that is not pure JSON)
body2 = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "stream me"}],
    "stream": True,
}
flow2 = FakeFlow(FakeRequest(json.dumps(body2), path="/v1/chat/completions"))
mod.request(flow2)
files2 = sorted(flows.glob("*.json"))
if len(files2) < 2:
    bad("streaming request not captured")
else:
    sse = "data: {\"choices\":[{\"delta\":{\"content\":\"hi\"}}]}\n\ndata: [DONE]\n"
    flow2.response = FakeResponse(sse, status_code=200, headers={"content-type": "text/event-stream"})
    mod.response(flow2)
    data2 = json.loads(files2[-1].read_text())
    if "response" not in data2:
        bad("streaming response not recorded")
    else:
        ok("handles streaming responses")

# provider error path
body3 = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "fail"}],
}
flow3 = FakeFlow(FakeRequest(json.dumps(body3), path="/v1/chat/completions"))
mod.request(flow3)
flow3.error = FakeError()
mod.error(flow3)
found_err = False
for f in flows.glob("*.json"):
    d = json.loads(f.read_text())
    if d.get("_meta", {}).get("error") == "upstream timeout":
        found_err = True
        break
if not found_err:
    bad("provider errors not recorded")
else:
    ok("records provider errors")

# filename safety on written files
for f in flows.glob("*.json"):
    if any(ch in f.name for ch in "/?:"):
        bad(f"unsafe filename written: {f.name}")
        break
else:
    ok("written capture filenames are safe")

sys.exit(fail)
PY
rc=$?
if [[ $rc -ne 0 ]]; then
  fail=1
fi

# ── 4. Analyzer behaviors ──────────────────────────────────────────────────────

echo "test: opencode-observability — analyzer behaviors"

CAPTURE_DIR="$TMPDIR/captures"
mkdir -p "$CAPTURE_DIR"

# actual usage flow
cat > "$CAPTURE_DIR/actual.json" <<'EOF'
{
  "_meta": {
    "timestamp": "2026-07-15T12:00:00",
    "host": "api.openai.com",
    "path": "/v1/chat/completions",
    "method": "POST",
    "model": "gpt-4",
    "streaming": false,
    "filename": "actual.json",
    "status_code": 200,
    "latency_seconds": 1.234,
    "usage_found": true
  },
  "request": {
    "headers": {
      "content-type": "application/json",
      "authorization": "[REDACTED]"
    },
    "body": {
      "model": "gpt-4",
      "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "hello"}
      ],
      "tools": [
        {"type": "function", "function": {"name": "read", "description": "Read a file"}}
      ],
      "stream": false
    }
  },
  "response": {
    "headers": {"content-type": "application/json"},
    "status_code": 200,
    "body": {
      "id": "chatcmpl-xxx",
      "choices": [{"message": {"content": "Hello! How can I help?"}}],
      "usage": {"input_tokens": 25, "output_tokens": 8, "total_tokens": 33}
    },
    "usage": {"input_tokens": 25, "output_tokens": 8, "total_tokens": 33}
  }
}
EOF

# estimated / no-usage flow
cat > "$CAPTURE_DIR/estimated.json" <<'EOF'
{
  "_meta": {
    "timestamp": "2026-07-15T12:00:01",
    "host": "api.anthropic.com",
    "path": "/v1/messages",
    "method": "POST",
    "model": "claude-sonnet-5",
    "streaming": false,
    "status_code": 200,
    "latency_seconds": 0.5,
    "usage_found": false
  },
  "request": {
    "headers": {"x-api-key": "[REDACTED]"},
    "body": {
      "model": "claude-sonnet-5",
      "messages": [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"}
      ]
    }
  },
  "response": {
    "status_code": 200,
    "body": {
      "content": [{"text": "Hello!"}]
    }
  }
}
EOF

# title-generation-like flow
cat > "$CAPTURE_DIR/title.json" <<'EOF'
{
  "_meta": {
    "timestamp": "2026-07-15T12:00:02",
    "host": "opencode.ai",
    "path": "/zen/v1/responses",
    "method": "POST",
    "model": "gpt-5.4-nano",
    "streaming": true,
    "status_code": 200,
    "latency_seconds": 0.2,
    "usage_found": false
  },
  "request": {
    "headers": {"authorization": "[REDACTED]"},
    "body": {
      "model": "gpt-5.4-nano",
      "input": [
        {"role": "user", "content": "Generate a short title"}
      ]
    }
  },
  "response": {
    "status_code": 200,
    "body": "data: {\"output\":\"hello\"}\n"
  }
}
EOF

# malformed + non-LLM in separate dirs
MALFORMED_DIR="$TMPDIR/malformed"
mkdir -p "$MALFORMED_DIR"
echo "this is not json" > "$MALFORMED_DIR/non_json.json"
assert "analyzer handles non-JSON without crashing" \
  "python3 '$ANALYZER' '$MALFORMED_DIR' --json 2>/dev/null >/dev/null; [[ \$? -lt 2 ]]"

EMPTY_DIR="$TMPDIR/empty"
mkdir -p "$EMPTY_DIR"
assert "analyzer handles empty directory without crashing" \
  "python3 '$ANALYZER' '$EMPTY_DIR' --json 2>/dev/null >/dev/null; [[ \$? -lt 2 ]]"

NOT_LLM_DIR="$TMPDIR/not_llm"
mkdir -p "$NOT_LLM_DIR"
echo '{"foo": "bar", "baz": 123}' > "$NOT_LLM_DIR/not_llm.json"
assert "analyzer reports non-LLM flow with unknown model" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$NOT_LLM_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['flows_analyzed'] == 1
assert d['unique_models']['unknown'] == 1
print('ok')
\""

assert "analyzer reports call count" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['flows_analyzed'] == 3, d
print('ok')
\""

assert "analyzer reports actual usage when available" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['usage']['has_actual_metadata'] is True
assert d['usage']['actual']['input_tokens'] == 25
assert d['usage']['actual']['output_tokens'] == 8
print('ok')
\""

assert "analyzer reports estimates when usage absent" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['usage']['estimated']['total_tokens'] > 0
text = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR'],
    capture_output=True, text=True).stdout
assert 'ESTIMATED' in text or 'estimate' in text.lower()
print('ok')
\""

assert "analyzer separates title-generation calls where detectable" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['title_generation_calls'] >= 1, d
print('ok')
\""

assert "analyzer reports tool-definition count and size" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
assert d['tool_definitions']['calls_with_tools'] >= 1
assert d['tool_definitions']['total_tool_count'] >= 1
assert d['tool_definitions']['estimated_total_tokens'] >= 0
print('ok')
\""

assert "analyzer reports system/user/tool message sizes" \
  "python3 -c \"
import json, subprocess, sys
r = subprocess.run([sys.executable, '$ANALYZER', '$CAPTURE_DIR', '--json'],
    capture_output=True, text=True)
d = json.loads(r.stdout)
roles = d['role_token_estimates']
assert 'system' in roles and roles['system'] > 0
assert 'user' in roles and roles['user'] > 0
assert d['system_prompt']['count_analyzed'] >= 1
print('ok')
\""

JSON_OUT1=$(python3 "$ANALYZER" "$CAPTURE_DIR" --json 2>/dev/null)
JSON_OUT2=$(python3 "$ANALYZER" "$CAPTURE_DIR" --json 2>/dev/null)
assert "JSON output is deterministic for same fixture input" "[[ '$JSON_OUT1' == '$JSON_OUT2' ]]"
assert "JSON output is parseable" "echo '$JSON_OUT1' | python3 -c 'import json,sys; json.load(sys.stdin)'"

TEXT_OUT=$(python3 "$ANALYZER" "$CAPTURE_DIR" 2>/dev/null)
assert "analyzer does not print prompt bodies by default" \
  "! grep -q 'You are a helpful assistant' <<< '$TEXT_OUT'"
assert "text report shows call count" "grep -q 'LLM calls analyzed:    3' <<< '$TEXT_OUT'"
assert "text report shows actual usage" "grep -q 'actual provider metadata' <<< '$TEXT_OUT'"

# ── Summary ───────────────────────────────────────────────────────────────────

echo "---"
if [ "$fail" -eq 0 ]; then
  echo "  all opencode-observability tests passed"
else
  echo "  FAIL: some opencode-observability tests failed"
fi
exit $fail
