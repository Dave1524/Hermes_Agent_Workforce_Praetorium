# OpenCode Observability

Measure actual OpenCode LLM prompt/tool/token overhead on Praetorium.

## Prerequisites

- **mitmproxy** 12.x: `pip3 install mitmproxy`
- **OpenCode** 1.17+: `opencode --version`
- **Python** 3.12+: `python3 --version`
- **mitmproxy CA certificate** generated (see below)

## Quick start

```bash
# Generate the mitmproxy CA cert (one-time)
mitmdump --listen-port 9453 -q &
sleep 2
kill %1

# Run OpenCode through the proxy
bin/opencode-observe run hello

# Analyze captures
python3 tools/opencode-observability/analyze_flows.py
```

## How it works

1. `bin/opencode-observe` starts `mitmdump` on `127.0.0.1:<port>` (default 9453).
2. It launches OpenCode with `HTTP_PROXY`/`HTTPS_PROXY` and `NODE_EXTRA_CA_CERTS` set.
3. The mitmproxy addon at `tools/opencode-observability/capture_addon.py` intercepts LLM API
   requests, detects them by looking for common shapes (`messages`, `input`, `prompt`, `contents`),
   and saves request/response JSON to `var/opencode-observability/flows/`.
4. When OpenCode exits, the proxy is automatically shut down.
5. `tools/opencode-observability/analyze_flows.py` reads the captures and produces a report.

## Running measurements

### Baseline measurement

```bash
# Fresh session, same prompt, agent by agent:

# 1. Built-in Build agent
bin/opencode-observe run hello

# 2. Built-in Plan agent
bin/opencode-observe run --agent plan hello

# 3. praetorium-planner
bin/opencode-observe -- @praetorium-planner hello

# 4. praetorium-developer
bin/opencode-observe -- @praetorium-developer hello

# 5. praetorium-qa
bin/opencode-observe -- @praetorium-qa hello
```

Then analyze each:

```bash
python3 tools/opencode-observability/analyze_flows.py
```

### Comparing agents

```bash
# After each measurement, move the captures to a named directory:
mv var/opencode-observability/flows var/opencode-observability/flows-build-agent

# Then analyze that directory:
python3 tools/opencode-observability/analyze_flows.py var/opencode-observability/flows-build-agent
```

### Full JSON output for comparison

```bash
python3 tools/opencode-observability/analyze_flows.py --json
```

### Inspecting prompt contents

```bash
python3 tools/opencode-observability/analyze_flows.py --prompts
```

## Certificate handling

The mitmproxy CA cert is at `~/.mitmproxy/mitmproxy-ca-cert.pem`.

The wrapper sets `NODE_EXTRA_CA_CERTS` to this cert only for the OpenCode child process.
The system trust store is never modified.

To regenerate the cert:

```bash
rm -rf ~/.mitmproxy
mitmdump --listen-port 9453 -q & sleep 2 && kill %1
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `OPENCODE_OBSERVE_PORT` | `9453` | Proxy listen port |
| `OPENCODE_OBSERVABILITY_DIR` | `$PWD/var` | Capture output root |
| `OPENCODE_CMD` | `opencode` | OpenCode binary |

`bin/opencode-observe` also accepts `--port`, `--dir`, and `--no-open` flags.

## Security

### Data captured

- LLM request bodies (prompts, messages, tool definitions, model parameters)
- LLM response bodies (completions, usage metadata)
- Request metadata: host, path, method, timestamps, latency
- Response headers (with sensitive values redacted)

### Data NOT captured

- HTTP `Authorization` headers (redacted)
- Cookies (redacted)
- Environment variables
- Secrets
- Non-LLM traffic is ignored

### Risks

- **Captured prompts and responses may contain business content.** Do not commit them.
- The capture directory (`var/opencode-observability/`) is `.gitignore`d, but verify before
  committing.
- Proxy runs on `127.0.0.1` only — not exposed to the network.
- TLS verification is not disabled globally; only `NODE_EXTRA_CA_CERTS` is used.

### Why captures must never be committed

The captured JSON files contain the full text of prompts sent to the LLM and the full text
of responses. If the LLM is used with business-sensitive or vault content, that content will
appear in the captures. These files are development tooling only — treat them as ephemeral.

## Cleaning up

```bash
# Remove all captured flows
rm -rf var/opencode-observability/

# Stop a proxy started with --no-open
kill $(pgrep -f "mitmdump.*capture_addon")
```

## Reproducing a baseline

To produce a reproducible baseline measurement:

1. Ensure the repository is on the same commit.
2. Use the same OpenCode version.
3. Use the same model configuration (`opencode.json`).
4. Use the same prompt text.
5. Run each measurement in a fresh shell (no stale context).
6. Clear captured flows between measurements: `rm -rf var/opencode-observability/flows/`

## Validation suite

Offline (default, no model spend) — included in `bin/verify.sh`:

```bash
bash tests/test_opencode_agents.sh
bash tests/test_opencode_observability.sh
bash bin/verify.sh
```

Live contract tests (opt-in, **spends model tokens**, uses a temporary fixture repo only):

```bash
OPENCODE_LIVE_TESTS=1 bash tests/test_opencode_agents_live.sh
```

Live scenarios:
- **A** planner on a harmless request (no file mutations, required headings)
- **B** developer on a tiny fixture change (intended files only, tests pass)
- **C** QA against a seeded defect (`FAIL`, no mutations)
- **D** minimal `hello` prompt × 3 runs for Build, Plan, planner, developer, QA (metrics recorded; exact token counts may differ)

## Files reference

| File | Purpose |
|---|---|
| `bin/opencode-observe` | Shell wrapper to start proxy and run OpenCode |
| `tools/opencode-observability/capture_addon.py` | Mitmproxy addon for LLM flow capture |
| `tools/opencode-observability/analyze_flows.py` | Flow analysis and report generator |
| `var/opencode-observability/flows/` | Captured flow JSON files (gitignored) |
| `.opencode/agents/praetorium-*.md` | Scoped OpenCode agents for cost measurement |
| `tests/test_opencode_agents.sh` | Offline agent config validation |
| `tests/test_opencode_observability.sh` | Offline addon/analyzer validation |
| `tests/test_opencode_agents_live.sh` | Opt-in live contract tests (token spend) |

## License

The capture addon (`capture_addon.py`) is adapted from
[agardnerIT/opencode-video-content](https://github.com/agardnerIT/opencode-video-content)
which is Apache-2.0 licensed.
