# Brief: Run augustus-content on the Buzz Augustus (NUC-46)

**Date:** 2026-08-12   **Verify:** `bash bin/verify.sh` (repo root, `~/dev/agent-workforce`)

## Problem

`augustus-content` runs on hermes → OpenRouter → `openai/gpt-5.5`, which has been returning
`402 Insufficient credits` on every call since ~2026-07-25. NUC-44 made that failure visible;
it did not make the job work. The board still has 10 `Picked` rows and nothing drafts them.

A second Augustus already runs on this box and is not on OpenRouter at all:
`buzz-agent@augustus` on the codex-acp harness (`gpt-5.6-sol`), with the same Editor-in-Chief
charter, his own engram memory, and the `qmd` MCP surface. Marginal inference cost on that
path is zero. This brief points the job at him.

Most of the wiring already exists and must not be rebuilt:

| Piece | State | Evidence |
|---|---|---|
| Content channel | `ROUTE_content=36dc03cb-…`, kind `45001`, `_notify=augustus` | `bin/buzz_routes.env` |
| augustus pubkey | `AGENT_augustus=d36e4b8b…` | `bin/buzz_agents.env` |
| praetorium may wake him | `[[rules]] name = "praetorium"`, `require_mention = true` | `~/.config/buzz-team/augustus.toml` |
| Publishing identity | `praetorium`, credential loaded only inside `bin/buzz_publish.sh` | `bin/deliver.sh:544` sends `--mention` |
| Runtime swap seam | `AGENT_RUNTIME_CMD`, runtime-agnostic | `bin/agent_propose.sh:234` |
| Artifact-check seam | `AGENT_VERIFY_CMD`, fails a lying exit 0 | `bin/agent_propose.sh:296` |

**The one hard blocker.** `buzz-agent@augustus` runs codex-acp inside a bwrap mount namespace
whose `--tmpfs ~/.config/agent-workforce` replaces the credential directory. He therefore
**cannot execute `bin/notion_rest.py`** — `load_token()` finds no `secrets.env`. He reaches
Notion only through `~/.config/buzz-team/buzz-notion-broker.py`, a host-namespace `--user`
unit that holds the token and answers one JSON line per connection on a 0600 unix socket at
`$XDG_RUNTIME_DIR/buzz-notion.sock`. That broker knows nothing of the NUC-44 guards, so a
naive migration silently routes around **both** of them.

**Chosen fix (Dave, 2026-08-12): give `notion_rest.py` a second transport.** The guards stay
in one file, in this repo, under this repo's gate, and augustus runs the identical command the
box-side jobs run. The broker is already the credential + policy owner on that side of the
namespace; this brief adds no policy to it and does not widen the namespace.

## Acceptance criteria

1. `bin/notion_rest.py` speaks the broker's socket protocol as an alternative transport. All
   five REST calls it makes are expressed as broker tools; behaviour is otherwise identical.
2. Transport selection is deterministic and announced, never a silent fallback:
   `--transport https|broker|auto` (default `auto`). `auto` = HTTPS when a token is readable,
   else the broker socket when it exists, else the existing hard error. The chosen transport
   is stated on stderr whenever it is not HTTPS.
3. **Both NUC-44 guards hold identically on the broker transport** — the `Drafted`/`Ready`/
   `Published` refusal and the `--max-rows` cap. They sit above the transport seam and are
   proven so by test on both paths.
4. A new `AGENT_RUNTIME_CMD` target dispatches the content task to buzz-augustus: publishes a
   trigger to `ROUTE_content` as `praetorium`, kind 45001, `--mention` augustus, then waits for
   completion.
5. **A dispatched run that produces nothing is a failure, not a decline.** Completion is
   either (a) the Notion board moved, or (b) augustus posted a reply beginning `DECLINE:`.
   Neither within the timeout ⇒ non-zero exit. A relay/publish failure exits `4` (`CRASH_EXIT`,
   recorded as `outcome=CRASHED`); dispatched-but-silent exits `1` (`outcome=FAIL`).
6. `AGENT_VERIFY_CMD` independently asserts the board moved since this run's marker, so a
   runtime that wrongly exits 0 is still caught (`bin/agent_propose.sh:296`).
7. `profiles/augustus_content_task.md` works unmodified from augustus's shell — the tool
   invocations in it resolve on the broker transport with no per-command flag to remember.
8. `bash bin/verify.sh` is green.

## Files to modify

- **`bin/notion_rest.py`** — the whole transport change lives behind the existing module-level
  `api(method, path, token, payload=None, timeout=30)` seam. Keep stdlib-only, keep
  `DATA_SOURCE_ID`, keep `cmd_*` untouched.
  - Add `broker_call(tool, arguments)`: connect `AF_UNIX` to
    `os.environ.get("BUZZ_NOTION_SOCKET", "/run/user/%d/buzz-notion.sock" % os.getuid())`,
    send `json.dumps({"tool": tool, "arguments": {...}}) + "\n"`, read one line, parse
    `{"ok": true, "value": …}` / `{"ok": false, "error": …}`. One request per connection —
    the broker's `Handler.handle()` does a single `readline` then writes and closes.
  - Add `api_via_broker(method, path, token, payload=None, timeout=30)` mapping the five calls:

    | current call | broker tool | arguments |
    |---|---|---|
    | `POST /data_sources/{id}/query` | `notion_query_data_source` | `data_source_id`, `filter`, `page_size` |
    | `GET /pages/{id}` | `notion_fetch` | `id`, `object_type: "page"` |
    | `PATCH /pages/{id}` | `notion_update_page` | `page_id`, `properties` |
    | `PATCH /blocks/{id}/children` | `notion_append_blocks` | `block_id`, `children` |
    | `POST /pages` | `notion_create_page` | `parent`, `properties`, `children` |

    An unmapped path is an error, never a pass-through — the broker exposes no raw REST and
    this must not invent one. Broker `{"ok": false}` becomes the same `sys.exit(...)` shape
    HTTPS errors already produce, so callers see one failure surface.
  - Add `--transport {https,broker,auto}` (default `auto`) as a **top-level** argument, before
    the subparser, so every subcommand gets it. Resolve once in `main()` and bind the module
    `api` accordingly. `load_token()` is skipped entirely on the broker transport — the broker
    owns the credential, and calling it would hard-exit inside augustus's namespace.
  - Broker `page_size` is validated to 1..100; `cmd_board` already sends 100. Do not raise it.

- **`profiles/augustus_content_task.md`** — no command changes (criterion 7 is satisfied by
  `auto`). Add a short note that on the Buzz harness Notion goes through the broker socket, so
  a `Buzz Notion credential is unavailable` error means the broker unit is down, not that the
  tool is misconfigured. Keep the NUC-44 "limits are enforced by the helper" block intact.

- **`docs/runbook.md`** — one row in the Job wiring table: `augustus-content` runtime becomes
  the Buzz dispatch, with the OpenRouter/hermes path named as the revert.

## Files to create

- **`bin/content_board_digest.sh`** — the single owner of "what does the board look like".
  Prints one stable `<page-id>:<status>` line per row, sorted, via
  `notion_rest.py board --json --max-rows 0`. Both the waiter and the verifier read this, so
  "the board moved" has exactly one definition. Fail-soft: on any read error print nothing and
  exit non-zero (an unreadable board is never "unchanged").

- **`bin/run_content_via_buzz.sh`** — the `AGENT_RUNTIME_CMD` target.
  1. Snapshot `content_board_digest.sh` and stamp a dispatch epoch.
  2. Publish the trigger through `bin/deliver.sh --route content` (or `buzz_publish.sh
     praetorium messages send` with `--kind 45001 --mention "$AGENT_augustus"`). The message is
     a short trigger, **not** the profile text: it tells augustus to read
     `~/agent-workforce/profiles/augustus_content_task.md` and execute it, and to reply
     `DECLINE: <reason>` if he judges there is nothing to do. One source of truth for the task;
     the profile is not resent nightly.
  3. Poll until `AGENT_BUZZ_WAIT_MINUTES` (default 20): re-digest the board, and read the
     channel for an augustus-authored event after the dispatch epoch.
  4. Exit 0 on board movement or a `DECLINE:` reply; `4` if the publish itself failed; `1` on
     timeout with neither.
  - **Use `buzz messages get --channel <uuid>`, never `buzz messages thread`** — thread only
    returns `e`-tagged replies, and a flat top-level answer reads as silence.
  - `--mention` of a non-member is fatal to the whole send, not a dropped tag; treat a publish
    rejection as exit `4`, never as "no reply yet".

- **`bin/content_moved.sh`** — the `AGENT_VERIFY_CMD` target. Compares the current digest
  against the pre-run snapshot the runtime left behind and exits non-zero when identical.
  Independent of the runtime's own verdict; this is the NUC-44 artifact check.

- **`tests/test_notion_rest_broker.sh`** + **`tests/test_notion_rest_broker.py`** — a stub
  broker on a temp `AF_UNIX` socket (stdlib `socketserver`, no network, no live Notion).
  Mirrors `tests/test_notion_rest.sh` → `.py` (a `.sh` driver is required; `bin/verify.sh` only
  executes `tests/*.sh`).

- **`tests/test_run_content_via_buzz.sh`** — stub `buzz` and stub digest on `PATH`.

## Test plan

- **The guards, twice.** Parametrize the NUC-44 assertions over both transports: `draft`
  refuses at `Drafted`/`Ready`/`Published` and appends nothing; `--force` overrides; `board`
  caps at 2 with the stderr notice; `--max-rows 0` returns all. A guard that holds on HTTPS and
  not on the broker is the entire risk this brief exists to avoid — pin it with one shared case
  table across both, so a future transport cannot be added without it.
- **Transport selection:** `auto` with a token → https; `auto` with no token and a live socket
  → broker, and says so on stderr; `auto` with neither → the existing hard error; explicit
  `--transport broker` with no socket → hard error, **never** a silent fall back to HTTPS.
- **Broker error surface:** `{"ok": false, "error": …}` exits non-zero with the message; a
  truncated/garbage line does too. No unmapped path reaches the socket.
- **Dispatch:** publish failure ⇒ exit 4; board moved ⇒ 0; `DECLINE:` reply ⇒ 0; timeout with
  neither ⇒ 1. Assert the trigger carries `--kind 45001` and `--mention <augustus-pubkey>`, and
  that the waiter reads `messages get`, not `messages thread`.
- **Repo `pipefail` rule** (`CLAUDE.md`): no early-exiting reader ends a pipeline; use the
  `shopt -po pipefail` scoping `assert()` and carry the `yes | grep -q y` canary in every new
  suite.
- Fixtures entirely local: stub `buzz` and stub broker on `PATH`/temp socket. No relay, no
  Notion, no OpenRouter.

## Out of scope / do not touch

- **`~/.config/buzz-team/buzz-notion-broker.py` and the rest of that tree.** The chosen design
  adds no policy there. It is machine-level infrastructure gated by
  `~/.config/buzz-team/verify-fleet.sh`, not by this repo's `bin/verify.sh`.
- **Never widen augustus's namespace** to hand `notion_rest.py` the token directly. Anything
  the bridge can read inside bwrap, the agent's own shell can read — that defeats the
  deny-list `verify-fleet` gate 5 exists to assert.
- **`~/.config/agent-workforce/augustus-content.env`** — deny-listed; no session can read or
  edit it. See preconditions: the cutover itself is Dave's.
- `buzz_routes.env` / `buzz_agents.env` / `augustus.toml` — the route, the pubkey and the
  filter rule are already correct. Changing a `filter` expression crash-loops the unit.
- Restoring OpenRouter credit, and the `augustus-content.timer` schedule.
- The Notion board's data, the vault, `.hermes/` profiles.

## Notes / preconditions

- **The cutover is a Dave-gated one-line edit.** `AGENT_RUNTIME_CMD` lives in
  `~/.config/agent-workforce/augustus-content.env`, which the deny-list blocks for every
  session including Bash. `/implement` lands the code and tests; it **cannot** flip the job
  over, and must not claim the migration is live. Report the exact line for Dave to paste.
- **The swap moves two jobs, not one.** `bin/content_change_dispatch.sh` invokes the same
  `agent_propose.sh` with the same `AGENT_JOB_OVERRIDES=augustus-content.env`, so the 15-min
  Picked poller migrates with the nightly. That is correct — two Augustuses drafting one board
  is the double-hosting hazard — but it means the 20-minute wait must coexist with a 15-minute
  tick. `agent_propose.sh`'s flock (`/tmp/agent_propose.lock`) makes the overlap a clean SKIP.
- **NUC-44 survives the swap untouched** and is why this is safe: `agent_propose.sh` records
  `CRASHED` for exit 4, `scorecard.sh` counts it, `content_change_dispatch.sh` holds
  `var/content_picked.state`, `deliver_content.sh` prints `run: FAILED`. Criterion 5's exit-code
  split is what feeds that chain — do not collapse 4 and 1 into one code.
- **Deploy is not automatic.** `bin/deploy` (rsync + atomic rename). Source edits alone leave
  systemd on old code.
- **A 15-min auto-sync timer does `git add -A` + commit + push to `origin/main`.** Commit
  immediately after editing or the message is lost to a generic `Auto-sync:` commit. It already
  swallowed part of NUC-44 today.
- Verified 2026-08-12 by reading the source: broker `HANDLERS` contains exactly the five tools
  the mapping table needs; the wire format is one JSON line each way; the socket is 0600 at
  `/run/user/<uid>/buzz-notion.sock`; `praetorium` is admitted in `augustus.toml`;
  `ROUTE_content` is kind 45001 notifying augustus.
- **Confirm before the first live run:** augustus is a member of channel
  `36dc03cb-5b24-45f6-b6d4-ac6de33c4621` (`buzz channels members`), and
  `buzz-notion-broker.service` is active. A mention of a non-member fails the whole send.
- Post-cutover smoke (manual, Dave): `systemctl start augustus-content.service`, then confirm
  `logs/cost.log` shows a real outcome and the board actually moved — not `CRASHED`.
