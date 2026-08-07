---
name: verify
description: Drive the delivery surface (bin/deliver.sh and its adapters) on the running box and capture receipts as evidence. Use when verifying a change to delivery, routing, or any systemd producer hook.
---

# Verifying the delivery surface

There is no app to launch here. The surface is **systemd + the relay**: a unit fires,
its `ExecStartPost`/`ExecStopPost` adapter runs, `bin/deliver.sh` posts to Discord, a
Buzz channel and Pulse, and writes one JSON receipt. The receipt plus a relay readback
is the evidence.

## Before driving anything: prove the three layers agree

Source `~/dev/agent-workforce` → runtime `~/agent-workforce` (`bin/deploy`) → installed
units `/etc/systemd/system` (`sudo cp` + `daemon-reload`). Nothing propagates on its own,
so a hook drive can silently exercise last week's code.

```bash
cd ~/dev/agent-workforce
while IFS=$'\t' read -r unit _; do
  case "$unit" in ''|\#*) continue;; esac
  diff -q "systemd/$unit" "/etc/systemd/system/$unit" || echo "UNIT DRIFT: $unit"
done < bin/buzz_producers.tsv
for f in bin/deliver*.sh bin/notify.sh bin/delivery_common.sh; do
  diff -q "$f" "$HOME/agent-workforce/$f" || echo "RUNTIME DRIFT: $f"
done
```

## Driving a hook without running the job

`./drive_hook.sh <unit> [KEY=VALUE ...]` reads the **installed** unit's `Environment=`
block back off systemd and execs the deployed hook under `env -i`. Unit env, adapter
logic, deliver.sh, route resolution, real transport and the receipt are all genuinely
exercised — only the `ExecStart` leg (the LLM job) is not. Say so in the report.

It does **not** load `EnvironmentFile=` (deny-listed secrets). That is usually what you
want; the exception is `agent-alert@`, which needs it — start that one for real.

Always redirect receipts to scratch and prefix the subject, so nothing you drive is
mistaken for a real report or manufactures a clean day for `bin/audit_buzz_dual_run.sh`:

```bash
./drive_hook.sh raw-ingest.service \
  "DELIVERY_RECEIPTS=$SCRATCH/receipts-verify.jsonl" \
  'REPORT_SUBJECT=[wiring-check] Raw ingest'
```

## Safe to start for real

- `overnight-pre-snapshot.service` — model-free, idempotent.
- `content-change-dispatch.service` — a Notion poll; usually a quiet tick, which is
  itself the thing worth observing (adapter logs `quiet tick — staying silent`, receipt
  count unchanged).
- `agent-alert@<anything>.service` — templated OnFailure handler, no side effects beyond
  a journal line and one alert delivery.

Never start: the `agent_propose.sh` jobs (cost, writes proposals into the vault inbox),
`scorecard.service` (git-pushes a rollup), `bd-followup-drafts.service` (its artifact is
real client content — drive discovery + the anchor, never the publish).

## Anchoring an artifact-lookup adapter

`file`/`status` adapters require the artifact to be newer than
`/home/dave/logs/run-markers/<unit>`. To make a past run's artifact deliverable, derive
the marker mtime from the artifact itself:

```bash
touch -d "@$(( $(stat -c %Y "$artifact") - 60 ))" "/home/dave/logs/run-markers/$unit"
```

**Do not hand-write a wall-clock timestamp** — the agent shell runs `TZ=UTC` while the box
is CEST, so `touch -d '2026-08-05 05:30'` lands two hours late and the adapter takes the
"this run wrote no record" branch. To force the *refusal* branch instead, `touch` the
marker bare (now) and leave the artifact old.

## Reading an event back off the relay

```bash
./bin/buzz_publish.sh praetorium messages get --channel <uuid> --limit 12 > out.json
```

- `messages get` has **no `--json` flag** — it is JSON already; passing it errors.
- **Redirect to a file.** `buzz ... | python3 - <<'PY'` silently yields nothing: the
  heredoc becomes python's stdin, so the piped JSON is discarded.
- **Never print raw `tags`.** Every agent-signed event carries
  `["auth",<owner-pubkey>,"",<sig>]`. Print `id`, `kind`, `content` only.
- Pulse threading: every note replies to the day root in `~/var/buzz-pulse-root`; check
  by fetching `buzz_publish.sh praetorium social event --event <pulse_event_id>` and
  printing only the `e` tags.

## Gotchas that have cost time here

- `local u=$1 mk=/path/$u` — `local`'s arguments expand **before** the assignments, so
  `$u` is empty and you touch the *directory*. deliver.sh then correctly reports
  `run marker missing`; the fault is the harness, not the code.
- Discord returns **429** under back-to-back sends. deliver.sh has no retry and files it
  as `discord_error`/`partial_success`. Space probe sends out, or read a bare `rc=1` from
  `hermes send --quiet` as rate limiting until proven otherwise (`--quiet` hides the body).
- `systemctl show -p Environment --value` emits shell-quoted entries; split with
  `shlex`, not on spaces, or quoted subjects are mangled.
