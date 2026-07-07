#!/usr/bin/env bash
# NUC-08 smoke test: prove a remote completion returns from this box.
# Runs the moment OPENROUTER_API_KEY exists in secrets.env. Never prints the key.
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
LOG_DIR="$HOME/agent-workforce/logs"
mkdir -p "$LOG_DIR"

[ -f "$SECRETS" ] || { echo "BLOCKED: $SECRETS missing — copy .env.example and fill values"; exit 2; }
# shellcheck disable=SC1090
source "$SECRETS"
[ -n "${OPENROUTER_API_KEY:-}" ] || { echo "BLOCKED: OPENROUTER_API_KEY empty in secrets.env"; exit 2; }

MODEL="${1:-${LLM_MODEL_BUSINESS:-}}"
[ -n "$MODEL" ] || { echo "BLOCKED: no model — pass as arg or set LLM_MODEL_BUSINESS"; exit 2; }
BASE_URL="${LLM_BASE_URL:-https://openrouter.ai/api/v1}"
MAX_TOKENS="${LLM_MAX_TOKENS_PER_CALL:-4096}"

# Tier-A enforcement (ratified NUC-07b): all four provider flags. Any one
# omitted reopens a silent fallback leak. only=[bedrock,azure] matches the
# ZDR-serving hosts for anthropic/claude-sonnet-5 as of 2026-07-06.
payload=$(cat <<JSON
{"model": "$MODEL",
 "max_tokens": $MAX_TOKENS,
 "provider": {"zdr": true, "data_collection": "deny",
              "only": ["amazon-bedrock", "azure"], "allow_fallbacks": false},
 "messages": [{"role": "user", "content": "Reply with exactly: PRAETORIUM-OK"}]}
JSON
)

start_ns=$(date +%s%N)
response=$(curl -sS --max-time 120 "$BASE_URL/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$payload")
latency_ms=$(( ($(date +%s%N) - start_ns) / 1000000 ))

content=$(echo "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])' 2>/dev/null) || {
  echo "FAIL: no completion in response (latency ${latency_ms}ms):"
  echo "$response" | head -5
  exit 1
}
usage=$(echo "$response" | python3 -c 'import json,sys; u=json.load(sys.stdin).get("usage",{}); print(f"prompt={u.get(\"prompt_tokens\",\"?\")} completion={u.get(\"completion_tokens\",\"?\")} total={u.get(\"total_tokens\",\"?\")}")' 2>/dev/null || echo "usage unavailable")

echo "OK model=$MODEL latency=${latency_ms}ms tokens: $usage"
echo "reply: $content"
echo "$(date -Is) smoke-test model=$MODEL latency_ms=$latency_ms $usage" >> "$LOG_DIR/llm_smoke.log"
