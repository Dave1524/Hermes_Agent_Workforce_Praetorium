#!/usr/bin/env bash
# Overnight job entrypoint, wired as AGENT_RUNTIME_CMD in
# ~/.config/agent-workforce/faceless_content.env.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_standing_research_topic_cc.sh" faceless-content
