# Agent board — refinement note (2026-09-23)

**Status:** refinement, not a brief. Nothing here is built. Written from a read of the repo,
the vault and the live Control Room on 2026-09-23; every claim below names where it was read.
The development plan follows once the decisions in §7 are taken.
**Revised later on 2026-09-23** after Dave's first review: the brief gate (§3.2a) was added; the
first draft had folded "the agent takes the idea further, Dave approves the plan" into a single
Ready click. §3.6 (the agent harness) was added on his second review, and with it run outcomes
moved off the card and onto a join with the receipt.
**Decided 2026-09-26**: all ten §7 decisions taken, by questionnaire. Three depart from the
recommended default; §7.1 names the resulting deltas to §3.6 and §8.
**Revised 2026-09-28** after an outside review of decision 4, which Dave pasted in and asked to
have incorporated. Dave now decides on the board. A card's work reaches the vault through the
agent-branch path the vault already ratified, and the Mac's merge watcher is the apply step
(§3.7). Decision 4 is revised, and three new decisions follow from it (§7, items 11-13). The
§7.1 deltas are now applied throughout, including the sites their first cut missed. The
development plan (§8) waits on decisions 11-13 and on gap 1, the one still open in §7.2.
**Revised again 2026-09-28**: Dave asked to open, read and edit a card in a popup inside the
Control Room. §3.8 designs it, adds a research date, and closes gap 4.
**Revised 2026-10-06**: Dave approved the popup mockup. §3.8 now carries its layout, as a
wireframe and as the mockup file beside this note. The research date's meaning became decision
14, and §8 now says which open item gates which increment: I1 waits on decisions 11, 13 and 14;
I9 also waits on decision 12 and gap 1.
**Decided later on 2026-10-06**: the rest of §7. Decisions 13 and 14 went as recommended.
Decision 11 went another way: the research is a page in a new Notion Research database, Dave
decides on the board and nowhere else, and may edit the page before approving it (16). What he
approves is copied into `05_knowledge/research/` (15). Decision 12 is the signature made and
checked by machines behind his click: one approval, no other step. Gap 1 is accepted for the
pilot. §3.7 is reworked to match, with every section that cited its branch draft. Nothing in
the design gates §8 any more; what remains before the first brief is listed under it.

## 1. The ask

A kanban board wired to the agent workspace on Praetorium, piloted on Claudius as a research
pipeline of topics. Cards configurable per request: title, description, a repo or vault
directory to connect to. Columns backlog / in progress / done, with the agent moving its own
cards. Dedicated agent tools and skills, plus a written workflow for the agent. Rendered in the
existing Control Room (`http://praetorium:8787/app/`). Later, the same board carries the other
agents' work with limited approval from Dave: Dave ideates and writes the initial description,
the agents design, architect and plan, Dave approves the plan, the agents build, test, verify
and review, Dave merges.

Inspiration (`docs/Kan_Ban_Board*.png`): Buffer's Ideas board (four plain columns, a card is a
title plus a description) and ClickUp's status board (parent list, assignee, priority,
subtasks). The Buffer shape is the pilot's; the ClickUp fields arrive with dev cards.

## 2. What is already on the box that this touches

**Three half-boards already exist for Claudius's research, and nothing joins them.**

| Half-board | Where | Who writes | What it holds |
|---|---|---|---|
| Backlog | `04_operations/box_brief/queue.md` + `standing_missions.md` (vault, read on the box over qmd) | Dave's Mac at EOD wrap; agents never edit | dated rows with Slug, Deadline, brief, acceptance bar, Status; the run picks the soonest-deadline OPEN row (`profiles/standing_research_cc_task.md` step 1-2) |
| In progress / outcome | `~/agent-workforce/var/workflow-receipts/<workflow>/<run>.json` | the runner (`bin/propose_receipt.py` → `bin/contract_exec.py`) | one receipt per run, exactly one terminal outcome, the artifact path |
| Review | the Notion Agent Inbox DB (`bin/agent_inbox_notion_sync.py`) and `_inbox/agents/_metrics/approvals.tsv` | the box syncs rows; Dave decides in Notion or with `agent_inbox.py promote|reject` on the Mac | New / Approved / Rejected per proposal; promoted / rejected / edited per slug |

`queue.md` already learned the lesson a board needs: **status is derived, not remembered**
(`00_system/tools/queue_reconcile.py`, written after one delivered row was re-picked every
weeknight for 34 days). Its two closure signals, a merge recorded against the row's Slug and a
passed Deadline, are the board's closure rules too.

**A kanban surface for these agents was built once and retired on 2026-09-02 (S3, D7).** The
retirement measured why (`design/archive/hermes-kanban-board.md`,
`.claude/briefs/archive/2026-09-02-hermes-kanban-retirement.md`):

- 11 cards in ten days, then 44 days idle; the board was never the input to a standing job.
- 5 of 11 cards were assigned to `engineer`, a profile that did not exist; they blocked forever.
  "Work the board could not route."
- 0 of 6 done cards carried a `result`. Done meant nothing.
- 0 of 11 cards used the per-card `skills` field the surface was built around.
- The gateway auto-dispatched `ready` cards every 60 s: an LLM as the poller, with same-day
  re-dispatch phantoms and stacked retries (`improvement-plan-2026-07-12.md` items 12, 15).
- The board was visible only through `hermes kanban list`; nobody looked.

**A live board-driven agent already exists, and it is the other precedent to copy from:**
Augustus works the Notion Content DB as his board. `bin/content_board_digest.sh` is the single
definition of "the board moved", `content_change_dispatch.sh` polls it cheaply every 15 minutes
and wakes him only on change. Its weakness is on record: board movement as the completion
signal is fragile (T7.2, "no board movement and no reply within 1200s").

**The Control Room's write model is fixed and must be respected.** The API is read-only by
construction (every write method 405) with exactly two POST seams: `/api/v1/control/actions`,
which hands a fixed verb vocabulary to the root-owned broker, and `/api/v1/control/proposals`,
which builds a `control-room/*` pull request from a preview token. The service runs as `dave`
with `ProtectHome=read-only`; the proposal worker got its own writable state root
(`/var/lib/control-room-proposals`, a drop-in) for exactly that reason. The SPA is React 19,
Vite, Tailwind 4, zod per endpoint, a hand-rolled router, committed build with a stamp gate
(`tests/test_control_room_spa.sh`). No board, card or column concept exists in it today.

**The vault's successor write path is already live, and the first drafts of this note missed
it.** Since the single-repo decision of 2026-08-12, agent work is meant to land as
`agents/<date>-<slug>` branches on the canonical repo. They carry file edits at real paths,
with no proposal prose. The Mac's `00_system/tools/agent_merge_watch.sh` (launchd
`com.vantagepoint.agent-promote`, hourly) merges the ones Dave approves in Notion (vault
`03_projects/active/ai_agent_workforce/agent_branch_workflow.md` §2-§6). The box pushes those
branches as the GitHub App `praetorium-vault-writer`, and `main` refuses it server-side. The
ruleset is `protect-main-agent-membrane`, with rules `update`, `deletion` and
`non_fast_forward` and the admin role as its only bypass (read 2026-09-28). The refusal probe
returned `GH013` on 2026-09-11. The scheduled runners have not cut over: `agent_propose.sh`
still writes `_inbox/agents/` on the box-safe mirror (`:24`, `:332`, `:510`), and the
migration runbook's §4 and §6-§8 are pending. §3.7 builds the board's apply step on the branch
path.

**The two execution surfaces a card can be worked on:**

- **S2**, scheduled headless Claude Code: `claude -p "$(cat profile)" --model claude-opus-5
  --permission-mode dontAsk --strict-mcp-config --mcp-config '{"mcpServers":{}}' --plugin-dir
  skills/claudius --allowedTools Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch`
  (`bin/run_standing_research_cc.sh:42-50`), wrapped by `bin/agent_propose.sh` (flock, retry,
  write boundary `_inbox/agents/**`, `AGENT_VERIFY_CMD`). No MCP. A board tool here is a CLI
  reached through Bash, nothing else.
- **S1**, the always-on Buzz session (`buzz-agent@claudius`): one MCP server, the per-agent
  bridge shim `buzz-team/buzz-team-mcp.py`, which advertises families (`qmd`, `notion`,
  `brave`) filtered by the manifest's `bridge_tools`. A board tool here is a new family in the
  shim, forwarding to the same CLI.

**This repo is public.** Card titles and bodies are client-derived; they never land here, not
in fixtures, not in docs, not in a ledger under `git`. The S3 export went to `~/OUTBOX/` for
this reason.

## 3. Proposed shape

**One sentence:** the board is a card ledger on the box where Dave drops an idea, a short brief
run turns it into a brief Dave approves, the existing standing-research run picks it up, and the
existing receipts and approvals close it, rendered in the Control Room, with the human touches
recorded as card events.

Not a fourth half-board. The successor of `queue.md` for research tasking, joined to the
receipts and the approval outcomes that already exist.

### 3.1 Card

Three kinds of field. Human-owned fields are written by Dave (or by Claude on the Mac at Dave's
say). The brief is negotiated: drafted by the agent from Dave's idea, edited by Dave, frozen by
Dave's approval, which pins the exact text it approved. Derived fields are computed from events
and decisions, and never edited. Dave's decisions are not fields at all: they live in the
broker's stream, outside the ledger (§3.7).

| Field | Owner | Notes |
|---|---|---|
| `id` | human, at create | the slug; the join key to receipts, artifact names and branch names, exactly as `queue.md`'s Slug column is today |
| `title`, `idea` | human, at create; editable (§3.8) | the idea is Dave's own text, one line or a page, as much as he knows; never rewritten by an agent |
| `brief` | negotiated | the task text the research run reads, in the standing-mission shape (Do / Acceptance / Sources / Size), drafted by the brief run from the idea and the card's `scope`, editable by Dave, frozen by `brief_approved`, which records the hash of the text it approved (§3.2a) |
| `kind` | human | `research` for the pilot; `dev` later |
| `owner` | human | a persona from `design/agents/`; validated at create: a live persona with a runner for this `kind` (the S3 `engineer` failure, made impossible) |
| `scope` | human | one or more of `vault:<dir>` / `repo:<name>`; for research a retrieval hint, what the brief run and the research run read first; for dev cards the writable worktree, enforced (§5); editable until the first research run (§3.8) |
| `deadline` | human, optional | absent means standing, never auto-closed (the `queue.md` discriminator) |
| `research_on` | human, optional | the research date: the research run does not pick the card before it (§3.8) |
| `priority`, `tags` | human, optional | priority is high, normal or low, normal when unset, and orders Todo; tags are free labels |
| `status` | derived | §3.2 |
| `events` | append-only | `created`, `brief`, `picked`, `note`, `edited`, each with actor, time, and run id where there is one; `brief` carries the hash of its text. Run outcomes are not events: a `picked` names its run, and that run's receipt says what happened (§3.6.1) |
| decisions | Dave, through the broker | `brief_approved`, `brief_returned`, `approved`, `changes_requested`, `rejected`, `blocked`, `unblocked`, each with its time and what it applies to: the brief's hash, and for an artifact approval the hash of the page text Dave approved, whose text the broker keeps beside it; signed, in the broker's root-owned stream, never in the ledger (decision 10, §3.7) |
| `runs`, `artifact`, `outcome` | derived: events joined to receipts, to the decisions and to canonical `main` | the artifact is the card's page in the Notion Research database (§3.7); what the card popup shows (§3.8) |

No per-card `skills` field. Skills belong to the persona manifest (`skills = [...]` per
workflow, T3.2); S3 measured the per-card version at zero use.

### 3.2 Columns, each derived

Dave named three columns, then asked for the gate his original ask already contained: the agent
takes the idea further, Dave approves the plan, only then is it worked. For a research card that
plan is a pre-research brief. The seven statuses that result are exactly the Notion Dev Plan's
own (`Backlog / Refine / Todo / In Progress / In Review / Done / Blocked`), so research and dev
cards share one vocabulary from day one and the later Dev Plan decision (§5) is about mirroring,
not translation. Each column waits on exactly one actor; that is the test for adding or
removing one.

| Column | Waits on | Derivation |
|---|---|---|
| Backlog | the agent | `created` with no current `brief`: none yet, the last one `brief_returned` (the next brief run reads the reason), or the idea or scope edited since it (§3.8) |
| Refine | Dave | a `brief` with no `brief_approved` for its hash; Dave edits (a new `brief`, actor dave), approves, or returns it |
| Todo | the timer | `brief_approved` whose hash matches the current `brief`; owner validated; ordered by priority, then deadline; a card whose research date is still ahead waits here, shown as scheduled, and the pick passes over it. A pick whose receipt says `failed` or `skipped` is void: the card is here again, without a strike. A `changes_requested` also returns the card here with Dave's note, and the next pick revises the card's page |
| In Progress | the run | `picked`, no receipt for that run yet, inside the runner's timeout; `pick` refuses a card whose brief no longer matches its approval |
| In Review | Dave | the last pick's receipt says `artifact` and names the card's published page, and the card is not Done. Until a decision covers the page as it stands, the card popup renders it beside the brief's acceptance lines and their answers, and offers Approve, Request changes and Reject (§3.7). An approved card waits here too, badged "approved, lands within the hour", until its note reaches `main`. That wait is the land step's and the Mac watcher's, not a column: two watcher cycles later it becomes a `merge-stale` exception naming Dave |
| Done | nobody | the card's note is on canonical `origin/main` with the approved hash, or `main`'s feed records `merged` for the card's branch; or the broker holds a `rejected`, shown as the card's outcome (decision 13), or as `withdrawn` when it was taken outside In Review (§3.8). For dev cards, a merged branch named for the id. Never from the agent's claim, and never from anything the box can write |
| Blocked | Dave | two `brief_returned`, two `changes_requested`, two picks whose receipts say `decline`, a deadline in the past, or a `blocked` decision. Only an `unblocked` decision lifts it; an edit never does |

Rules carried over from `queue.md`: a dated card cannot outlive its deadline; a standing card is
never reaped; a card returned or declined twice at the same gate stops moving until Dave touches
it, so a faulty idea or brief costs two turns, not thirty-four nights.

### 3.2a The brief gate

**What the brief is.** The standing-mission shape (`standing_missions.md` M1-M4: Do /
Acceptance / Cadence), extended with what a pre-research brief has to settle:

- Question: the research question, sharpened from the idea.
- Why: the decision or project it feeds, read from the card's `scope` in the vault (for the
  worked example below, `05_knowledge/` over qmd).
- Scope in / out.
- Sources: vault paths to read; web query lines, de-identified per `docs/data_boundary.md`.
- Acceptance: three to five checkable statements, M1-style. In Review renders the page's
  answers against them, which is the "result" S3's done cards never had.
- Size: fits one run, or a proposed split into N cards for Dave to create.
- Questions for Dave: what the vault does not say and the agent needs. This is where "it
  depends how much I know" lives: Dave answers by editing, then approves.

If Dave already knows enough, he writes the brief at create and the card starts in Refine (one
click to approve) or, with "create and approve", in Todo: the popup's create, followed by the
broker's approval. Either way the approval pins a hash; who wrote the text is provenance on the
event, not a different path.

**Who writes it and when.** A second S2 workflow, `research-brief`, with its own profile,
contract and receipt. Its timer's pre-flight is model-free (`board.py next --column backlog
--owner claudius`): a quiet tick is a `skipped` receipt and no model starts; a Backlog card
starts a short run (Read, Grep, qmd over `scope`, and WebSearch / WebFetch for a landscape
check, decision 9) that ends in one `brief` event, recorded by the wrapper from the run's
output file, never from the model's say-so. That is `content_change_dispatch.sh`'s rule
(NUC-35: deterministic poll, inference only on change) applied to a local ledger instead of
Notion, which drops the fail-soft remote-read handling that makes the Notion version
delicate. Hourly on weekdays is enough for the pilot; a systemd `.path` unit on the ledger
would make it immediate, at the price of the first path unit in the repo. Folding the brief
into the 04:30 run was rejected: it costs a night per gate and gives one run two outcomes,
which the receipt shape forbids. The Buzz session is the natural
home for the conversational version, where Claudius can ask before he drafts. It needs the
bridge family, and is in from day one (decision 7), beside the asynchronous path Dave
described: he drops the idea, the agent picks it up.

**Worked example** (synthetic, like the mockup's card). Idea card at 10:00: "can the vault
search run locally instead of over an API, and what would it cost to keep fresh?", `scope =
vault:05_knowledge`. Brief by 11:00, with two questions
for Dave. He answers them inline at 18:00 and approves. At 04:30 the research run picks the
card, and by breakfast its page is in the Research database and the card is In Review. Dave
reads it, fixes a sentence in Notion and approves on the card; within the hour the note is in
`05_knowledge/research/`: Done. One extra half-day per card buys an approved acceptance bar for
the research run, instead of one it has to infer.

### 3.3 Actors and gates

| Actor | Does | Through |
|---|---|---|
| Dave | create and edit cards, refine, approve or return a brief, decide on the artifact (approve, request changes, reject), withdraw, block, unblock | the Control Room board and its card popup (§3.8); every decision goes to the broker (decision 10); he may edit a card's Notion page before approving it (decision 16). The Notion Agent Inbox stays the decision surface for branches and proposals no card owns |
| Claude on the Mac (cockpit) | drafts and edits cards at Dave's say, prepares briefs | the same HTTP seam over the tailnet (`create`, `brief`, `note`, `edit`), or the CLI over ssh; never a decision, by rule; gap 1 is accepted for the pilot (§7.2) |
| the board sweep | lands each approval: the approved text as one new note on a card branch, pushed as the App; marks a page merged or rejected | `board.py land` and `sweep`, model-free, from the broker's copy of the text (§3.7) |
| the Mac merge watcher | applies Dave's approvals: merges a landed card note into `main` | `agent_merge_watch.sh`'s board pass, as Dave, after checking the broker's signature and the note's hash (§3.7) |
| the runner (`agent_propose.sh` + the per-job wrapper) | `picked`; for the brief run `brief`; for a card run the publish of its page; the `card` block in the receipt | the CLI and `notion_research.py`, from the wrapper, never left to the model; run outcomes stay in the receipt |
| Claudius, S2 brief run | reads a Backlog card and its `scope`, checks the landscape on the web, writes the brief to its output file | Read, Grep, qmd over Bash, WebSearch, WebFetch; the wrapper turns the file into the `brief` event |
| Claudius, S2 research run | reads the approved brief, and after a request for changes the current page; writes `research.md` with the acceptance answers; may write notes | files only; the wrapper publishes the page and records the notes |
| Claudius, S1 | lists, drafts Backlog cards and briefs from a conversation, appends notes | the `board` family in the bridge shim |

Two human touches on a research card: approve the brief, and decide on the artifact. Landing and
merging are machinery (§3.7). A dev card adds the merge approval as a third (§5). Each touch is
a signed broker decision with a time, which is what "limited approval" needs to stay auditable.
The idea at create is the one other thing Dave writes, and the only free text the agent does not
draft.

### 3.4 Store and seams

- **Store:** an append-only event ledger, one directory per card, under a dave-owned state
  root outside git and outside the deployed tree, on the pattern of
  `/var/lib/control-room-proposals`: `control-room.service` cannot write under `~` and the
  runner runs as `dave`, so the root must be writable by both. Off-box reads are the API.
  Backup joins the `var/` inventory (runbook § What must be backed up).
- **One owner of the shape:** `bin/board.py`, the way `bin/workflow_receipt.py` owns the
  receipt. Derivation of status is one function in it and nowhere else. Every ledger writer
  (runner, HTTP seam, bridge family) calls it; no second implementation of the rules. Dave's
  decisions have their own owner, the broker (§3.6.1).
- **HTTP seam:** a third POST route beside actions and proposals, `POST
  /api/v1/control/board`, with the same shape check, peer gate and `X-Control-Room: 1` header.
  It forwards `create`, `brief`, `note` and `edit` to `board.py`, and Dave's decisions to the
  broker (decision 10, §3.7), the same fork `/api/v1/control/actions` already makes.
- **Reads:** `GET /api/v1/board`, `GET /api/v1/board/<id>`, joined server-side to receipts
  (`card` in the receipt, §3.6), to the broker's decisions and to canonical `main`, so the card
  popup shows its runs and its page, read from Notion when the popup opens, and a run page names
  its card. `GET /api/v1/board/decisions` serves the signed decisions the Mac watcher applies
  (§3.7).
- **Artifact store:** the Notion Research database, one page per card. From the box only the
  wrapper's publish and the sweep's marks write it; Dave may edit a page before approving it
  (decision 16). Its id sits in the box's configuration beside the Notion token, outside git.
- **Bridge family (S1, from day one, decision 7):** `board` added to `FAMILIES` in
  `buzz-team/buzz-team-mcp.py`, tools `board_list`, `board_get`, `board_create` (Backlog
  only), `board_brief` (a `brief` event on a Backlog or Refine card, never an approval),
  `board_note`; enabled per manifest through `bridge_tools`.

### 3.5 The pilot flow on S2, end to end

1. Dave creates a card in the Control Room's popup (or asks Claude on the Mac to draft one):
   title, idea, kind, owner, scope, and optionally a research date and a deadline. It lands in
   Backlog. `create` refuses when the owner has no runner for the kind.
2. `research-brief.timer` ticks hourly on weekdays. The pre-flight asks `board.py next
   --column backlog --owner claudius`; nothing means a `skipped` receipt and no model. A card
   means a short run, web tools included (decision 9), that writes the brief to its output
   file; the wrapper records it as a `brief` event. Refine.
3. Dave reads the brief in the card popup, answers its questions inline, and approves, or
   returns it with a reason. Both are broker decisions, and the approval pins the hash. Todo.
4. `agent-proposal.timer` fires Mon-Fri 04:30 as today. Before the model starts,
   `run_standing_research_cc.sh` (or `agent_propose.sh`, one of the two, not both) asks
   `board.py pick --owner claudius --kind research` for the top Todo card whose research date
   has come, checks the approved hash against the current brief, writes `picked` with the run
   id, and exports `AGENT_CARD=<id>`. No such card means the profile falls through to standing
   missions and to `DECLINE:`, exactly as now.
5. The profile's step 1 reads the picked card and its brief (`board.py show "$AGENT_CARD"`)
   instead of `queue.md`. Standing missions stay as they are. With a card, the run writes one
   file, `research.md`: the findings, the brief's acceptance lines answered one by one, and the
   sources (§3.7). After a request for changes it starts from the current page, Dave's edits
   included. Without a card, the mandated artifact keeps its fixed filename
   `_inbox/agents/<date>_standing-research.md`, since the contract's determinism rests on it.
6. After the model exits, the wrapper publishes `research.md` as the card's page in the
   Research database. `propose_receipt.py` already knows the outcome; it writes the `card`
   block, with the page and the published hash, into the receipt, and the card's column follows
   from that receipt. Nothing is copied onto the card; the model never touches Notion or git,
   and never reports its own completion.
7. Dave reads the page, in Notion or in the popup beside the acceptance answers, edits it if he
   likes, and approves, requests changes or rejects. The sweep lands an approval as one note on
   a card branch, and within the hour the Mac watcher merges it (§3.7). Done is read from
   `main`. Delivery posts one notice line naming the card, never the research, and the Agent
   Inbox sync never sees a card's branch.
8. The Control Room board page shows the seven columns; the card popup (§3.8) shows idea,
   brief with its provenance, events and decisions, runs, and the page against the acceptance
   lines, and edits the card; exceptions, the ten kinds §3.6.8's sweep raises, join the
   existing queue.

One new timer, model-free unless a Backlog card exists; no LLM poller. The improvement plan's
rule holds: cheap checks on a timer, inference only when there is a card, and the existing
04:30 cadence stays the research dispatch.

### 3.6 The agent harness: tool, wrappers, profiles, manifest, skills, bridge, contracts

Design, not implementation. Every seam named here was read on 2026-09-23: what
`agent_propose.sh` exports to the model, how a second scheduled job is wired, how a manifest
entry, a pointer skill and a bridge family are shaped, what the receipt and contract executors
accept. Where a design choice rests on one of those facts, the fact is cited.

#### 3.6.1 The tool: `bin/board.py`

One file owns the ledger's shape, its derivation and its CLI, the way `bin/workflow_receipt.py`
owns the receipt. The wrappers, the HTTP seam and the bridge family call it; nothing
re-implements a rule.

Layout under `$BOARD_ROOT` (`/var/lib/control-room-board`, §3.6.9):

```
cards/<id>/card.json          # the human fields at create
cards/<id>/events.jsonl       # append-only, one JSON object per line
cards/<id>/briefs/<hash>.md   # every brief text ever recorded, by the hash of its normalised bytes
runs/<run_id>/                # the per-run scratch: card.md, brief.out.md, research.md, research.prev.md, notes.md
```

A ledger event is `{ts, event, actor, run_id?, workflow?, hash?, reason?, fields?}`. The actor
vocabulary is closed: `dave`, `mac:claude`, `run:<run_id>`, `buzz:<agent>`. The sweep writes no
events. Dave's decisions are not ledger events and do not live under `$BOARD_ROOT` (below).

| Verb | Caller | Writes |
|---|---|---|
| `create --kind --owner --scope … [--brief FILE]` | the seam (Dave, Claude on the Mac), the bridge family | `created`; with `--brief` also `brief`. The popup's "create and approve" follows it with the broker's approval |
| `list`, `show <id>`, `next --column --owner --kind`, `status <id>`, `decisions [--unapplied]` | anyone; read-only; all but `decisions` are the only verbs a model session is told about | nothing; `decisions` reads the broker's stream joined to `main`, which `GET /api/v1/board/decisions` serves |
| `template --kind research` | anyone | nothing; prints the brief skeleton, the single owner of the required headings |
| `validate-brief FILE --card <id>` | the verify command | nothing; exit 1 names the missing heading or the acceptance-line count |
| `brief <id> --from-file FILE --actor` | the brief wrapper after the model exits; the seam (Dave's edit); the bridge family | `brief` with the hash; the text to `briefs/<hash>.md`; refuses a text whose hash equals a returned one |
| `pick --owner --kind --column --run-id --workflow` | `agent_propose.sh`, before the model | `picked`; renders `runs/<run_id>/card.md`, with Dave's note after a request for changes; refuses a Todo card whose brief no longer matches its approval and records the exception; passes over a card whose research date is still ahead |
| `note <id> --from-file --actor` | the research wrapper after the model (from `notes.md`); the bridge family; the seam (Dave's note in the popup) | `note` |
| `edit <id> --expect-rev N --field value …` | the seam (Dave, Claude on the Mac); refused for every other actor | `edited` with the changed fields; refuses `id`, `owner` and `kind`, idea and scope after the first research run, anything but title, tags and priority while In Progress, a research date after the deadline, and a stale revision (§3.8) |
| `land [<id>]` | the sweep | nothing in the ledger: for each approval not yet landed, the broker's copy of the approved text, checked against the signed hash, written as the one note `05_knowledge/research/<id>.md` with its front matter on `agents/<date>-card-<id>`, cut from a fresh `origin/main` and pushed as the App; idempotent per decision (§3.7) |
| `sweep` | `workflow-receipt-sweep.timer`, beside `receipt_sweep.py` | nothing in the ledger: runs `land`, fetches canonical `main` for Done, marks a card's page merged or rejected, sends exceptions to the incident stream; never a column |

**Decisions are not ledger events.** The seven verbs only Dave may take are broker verbs
(decision 10): approve or return a brief; approve, request changes on, or reject an artifact;
block; unblock. Withdraw (§3.8) is a `rejected` taken outside In Review, not an eighth verb.
The broker appends each one, signed (decision 12), to its own root-owned, world-readable
stream under `/var/lib/control-room/receipts/board/`, and never executes `board.py`. `derive()`
reads that stream and trusts a decision from nowhere else. A decision-shaped event in the
ledger is a `forged-decision` exception, never a transition.

**Derivation joins receipts, decisions and `main`.** `derive(card, events, decisions,
receipts, main)` is one pure function, and run outcomes are never copied onto a card: a
`picked` names its run id and workflow, and the
column follows from that run's receipt at `<receipt root>/<workflow>/<run_id>.json`, read
through `workflow_receipt.py`. No receipt yet, inside the runner's timeout, is In Progress;
`artifact` is In Review; `decline` is a strike and the card returns to Todo; `failed` or
`skipped` voids the pick without a strike, the card returns to Todo, and the failure stays
the receipt's business, already alerted and already an incident. A pick past the timeout with
no receipt is a `stale-pick` exception. The receipt root resolves exactly as `contract_exec.py`
resolves it (`CONTROL_ROOM_RECEIPT_ROOT`, else `~/agent-workforce/var/workflow-receipts`).
The earlier draft had the wrapper write `artifact` and `declined` onto the card; that was a
second copy of a fact the receipt already owns, and it is gone. Done is a join too, with
canonical `main` (§3.7), never an event.

Hashing: sha256 over the brief with trailing whitespace stripped and LF endings; the brief
approval carries it, `pick` checks it, the receipt records it. An artifact approval pins the
page text the popup rendered, hashed the same way. Appends take `flock` on the card directory;
derivation is order-independent, so the seam approving while the timer picks cannot corrupt a
card. `board.py --help` is the S2 mechanism document: verbs, the actor rule, the run-scratch
layout, the template. The profile points at it; nothing else describes the mechanism.

#### 3.6.2 What each surface sees, and what it may touch

| Surface | Reads | Writes | Never | Held by |
|---|---|---|---|---|
| S2 brief run (`research-brief`) | `$AGENT_CARD_DIR/card.md` (idea, scope, returned reasons); the scope over qmd; the web, for a landscape check (decision 9); `board.py template` | `$AGENT_CARD_DIR/brief.out.md`, nothing else | the ledger; `_inbox/agents/`; the vault | `--allowedTools Bash,Read,Write,Glob,Grep,WebSearch,WebFetch`; the ledger-growth detector; `mirror-was-not-dirty` |
| S2 research run (`agent-proposal`) | `$AGENT_CARD_DIR/card.md` with the approved brief, and `research.prev.md` after a request for changes; the vault; the web, as today | with a card, `$AGENT_CARD_DIR/research.md`; without one, the one proposal file in `_inbox/agents/`; `$AGENT_CARD_DIR/notes.md` | the ledger; Notion; git; on a card run, the vault | the write boundary, which on a card run is `$AGENT_CARD_DIR`; the ledger-growth detector; the wrapper alone publishes |
| S1 Buzz session | `board_list`, `board_get` | `board_create` (Backlog), `board_brief`, `board_note` | `pick`; `edit`; every decision | the family advertises five tools; the settings deny list `fleet_capabilities.py` renders denies the rest a second time; decisions are broker-only |
| Control Room | the read model; the card's Notion page, read-only | `create`, `brief`, `note`, `edit` through `board.py`, as `dave`; Dave's decisions through the broker | `pick` | the seam's verb table, peer gate and header; the broker's allowlist |
| board sweep (`board.py land`, `sweep`) | the broker's stream and its copies of approved texts; canonical `main`; the card's page | a card branch adding one note, pushed as the App; the page's merged path or rejected mark | the ledger; any vault path but the card's note; `main` | model-free; `land` refuses a text whose hash is not the signed one; the ruleset refuses `main` to the App |
| Mac merge watcher | signed approvals (`GET /api/v1/board/decisions`), the card's landed branch | `main`: the merge of a verified branch and its feed line | an unsigned decision; a branch that does more than add the card's note; a body whose hash is not the signed one | the signature check against the pinned public key; `agent_branch.py`'s guards; the ruleset, for every other writer |

A model session, on either surface, is never handed a write verb of the ledger, nor any
decision. On S2 it writes files and the wrapper converts them after the model exits; on S1
the shim owns the verbs. That is the shape `_inbox/agents/**` already has: the model's writes
land where the wrapper inspects them, and the wrapper decides what becomes an event.

#### 3.6.3 Wrapper changes

`bin/agent_propose.sh`, five additions, each opt-in by env, none touching a job that does not
set them:

1. **One run id, early.** `export AGENT_RUN_ID="${AGENT_RUN_ID:-${INVOCATION_ID:-hand-$AGENT_RUN_STARTED_AT}}"`
   before the pre-flight. `propose_receipt.py:130` already prefers `AGENT_RUN_ID`, so the
   card's `picked` and the receipt name the same run without a second resolver.
2. **`AGENT_BOARD_PICK="--owner claudius --kind research --column todo"`.** After the
   `requires` pre-flight (`:309-327`) and before the checkout: `board.py pick $AGENT_BOARD_PICK
   --run-id "$AGENT_RUN_ID" --workflow "$AGENT_TASK_SLUG"`, then `export AGENT_CARD
   AGENT_CARD_DIR BOARD_ROOT`. The override file's variables never reach the model's
   environment (the wrapper sources them without `set -a`), so these three exports are
   explicit and are the whole card-side environment a profile may name. No card: with
   `AGENT_BOARD_REQUIRED=1` the run ends as `write_receipt SKIP --reason "no card in
   backlog"`, the flock skip's receipted path (`:201`, outcome `skipped`); without it the run
   proceeds card-less and the profile falls through, as standing research does today. A tick
   that lands while the 04:30 job holds the fleet lock is the ordinary lock skip and tries
   again next tick.
3. **`AGENT_RUN_MODE=board`.** A third mode beside `proposal` and `ops` (`:223-227`): lock
   and pre-flight as `ops` (no inbox checkout, no write boundary, no commit, no
   `deliver_proposal.sh`), the pick required, the model, the verify command, then one of two
   outcome words. `BOARD` when `$AGENT_CARD_DIR/brief.out.md` is newer than
   `AGENT_RUN_STARTED_AT`: the wrapper runs `board.py brief "$AGENT_CARD" --from-file … --actor
   "run:$AGENT_RUN_ID"` and `propose_receipt.py` maps `BOARD` to `--artifact
   "board://$AGENT_CARD/brief/<hash>"`. Otherwise `NOPROPOSAL`, the decline path it has.
4. **The ledger-growth detector.** The line count of `cards/$AGENT_CARD/events.jsonl` taken
   before the model and compared after every attempt. Growth during the model phase is
   `VIOLATION`: the same word and the same discard the write boundary uses (`:486-494`), with
   the offending lines moved to `runs/<run_id>/rejected-events.jsonl` rather than deleted, so
   the incident names what was attempted.
5. **A card run publishes a page (decision 11).** When the pick returns a card in `proposal`
   mode, the wrapper skips the inbox checkout and runs the model in `$AGENT_CARD_DIR`. After a
   request for changes it first exports the card's current page, Dave's edits included, to
   `research.prev.md` through `bin/notion_research.py export`. After the model exits, the
   mirror must be clean and the ledger unchanged, the brief run's two checks; anything else is
   `VIOLATION`, with the same discard. The wrapper then runs `notion_research.py publish --card
   "$AGENT_CARD" --from-file research.md`, which creates the card's page in the Research
   database or rewrites its body, idempotent per card and run: `bin/notion_daily.py`'s pattern,
   keyed by card instead of date. `propose_receipt.py` records the page and the published hash
   as the artifact. No git happens in a run; the branch is the land step's (§3.7). A card-less
   run takes today's inbox path, untouched.

`bin/run_research_brief_cc.sh`, on `run_standing_research_cc.sh:34-50` line for line where it
can be: the `-r` guards on the profile and on `.claude-plugin/plugin.json` (`tests/test_pointer_skills.sh`
demands both), `--plugin-dir "$SKILLS_DIR"`, `--strict-mcp-config` with the empty server
list, `--session-id`, `--model claude-opus-5` (judgment, short; revisit against the
approved-without-edit rate), `--allowedTools "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"`:
no `Edit`; the web tools are decision 9.
It runs `vault_sync_guard.sh check` first, as `run_raw_ingest_cc.sh:26` does, and `cd`s to
`$AGENT_CARD_DIR`, never the inbox worktree.

`bin/brief_or_decline.sh`, the `AGENT_VERIFY_CMD`, with `proposal_or_decline.sh`'s exit
contract: 0 when `brief.out.md` is this run's and `board.py validate-brief` accepts it, or the
attempt log carries this run's own `^DECLINE:`; 3 on this run's `^skip:`; 1 on neither.

Units. `systemd/research-brief.timer`: `OnCalendar=Mon..Fri 08..18:07` (hourly, decision 5),
`RandomizedDelaySec=3min`, `Persistent=false` (a missed tick must not fire at boot).
`systemd/research-brief.service`, cloned from `m1-signal-scan.service`:
`AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/research_brief.env`,
`ConditionPathExists=/var/lib/control-room-board` instead of the inbox worktree (the job never
touches it), `OnFailure=agent-alert@%n.service`, `TimeoutStartSec=20min`, and an
`ExecStartPost` through the `notify.sh` adapter posting one line to the research route ("card
`<id>`: brief in Refine"), never the brief body; that makes it a Buzz producer, so
`bin/buzz_producers.tsv` gets its row. `profiles/research_brief.env.example`:
`AGENT_RUN_MODE=board`, `AGENT_BOARD_PICK="--owner claudius --kind research --column backlog"`,
`AGENT_BOARD_REQUIRED=1`, `AGENT_TASK_SLUG=research-brief`, `AGENT_OWNER=claudius`,
`AGENT_RUNTIME_CMD`, `AGENT_VERIFY_CMD`, `AGENT_MAX_ATTEMPTS=2`.

`standing_research.env` gains one line, `AGENT_BOARD_PICK="--owner claudius --kind research
--column todo"`: the mode stays `proposal`, the pick is optional, a picked card switches the
run to its page (item 5), and `propose_receipt.py` reads `AGENT_CARD` to write the receipt's
`card` block.

#### 3.6.4 Profiles: the agent's workflow description

`profiles/research_brief_cc_task.md`, first line `Owner: claudius — …`
(`tests/test_fleet_ownership.sh` W2), in the house shape of an owner line, a runtime paragraph
and numbered steps, tools named as `python3 ~/agent-workforce/bin/…` (the deployed path, the
convention every profile follows):

- STEP 0. `$AGENT_CARD` unset: print `skip: no card` and stop. Read `$AGENT_CARD_DIR/card.md`
  in full. A brief by this run id already on it: print the skip line and stop.
- 1. Ground. `qmd` over the card's `scope` first, then `04_operations/current_priorities.md`
  and `open_loops.md` for the decision the idea feeds. Then the landscape, with WebSearch and
  WebFetch, on queries de-identified per `docs/data_boundary.md` (generic public names only). A
  `returned` reason is the previous brief's verdict; answer it.
- 2. Duplicates. `python3 ~/agent-workforce/bin/board.py list --owner claudius --kind research`
  and the last five `_inbox/agents/*_standing-research.md` over qmd; an idea already in Todo,
  In Review or Done, or already proposed, is `DECLINE: duplicate of <id>`, not a brief.
- 3. `python3 ~/agent-workforce/bin/board.py template --kind research`, then fill every
  heading: three to five acceptance lines, each checkable from the artifact alone; `## Questions
  for Dave` is where the run stops guessing; `## Size` says one run or proposes a split.
- 4. Write exactly `$AGENT_CARD_DIR/brief.out.md` and nothing else, anywhere. Never call
  `board.py` with any verb but `list`, `show` and `template`.
- 5. Decline when the idea is not intelligible enough to ask a question about, when the scope
  path does not exist on the mirror, or on a duplicate: `DECLINE: <reason>` on its own line.
- Never act outward; the closing paragraph every profile carries.

`profiles/standing_research_cc_task.md`, the diff. STEP 0 unchanged. Step 1: with
`$AGENT_CARD` set, `$AGENT_CARD_DIR/card.md` is the tasking and its brief the acceptance bar,
and the queue is not read; without it, standing missions as today. The `queue.md` bullet
leaves with decision 2, and `tests/test_standing_research_smoke.sh`'s assertion that the
profile names `queue.md` flips with it. Step 2 loses (a). Step 4, with a card: write
`$AGENT_CARD_DIR/research.md`, a first line naming the card id and the question, the findings,
then each acceptance line in the brief's order answered `MET` / `PARTLY` / `NOT MET` with the
finding it rests on, then the sources. After a request for changes, revise `research.prev.md`
rather than start over, and keep what Dave edited. Never touch Notion, git or the vault. Without
a card, step 4 is unchanged. Anything worth keeping on the card that is not a finding goes to
`$AGENT_CARD_DIR/notes.md`.

#### 3.6.5 Manifest

`design/agents/claudius.toml` gains one `[[workflows]]` entry:

```toml
[[workflows]]
unit     = "research-brief"
surface  = "scheduled"
trigger  = "Mon..Fri 08-18 hourly (+3min jitter)"
model    = "claude-opus-5"
profile  = "profiles/research_brief_cc_task.md"
runner   = "bin/run_research_brief_cc.sh"
route    = "research"        # one notice line, never a forum post of the brief
web      = true              # decision 9
board    = "research"        # new key, below
contract = "design/contracts/research-brief.md"
status   = "standing"
suite    = ["tests/test_research_brief_smoke.sh"]
skills   = ["investment-research", "meeting-prep", "prospect-research"]
notes    = "A quiet tick is receipted skipped before any model; the model runs only when Backlog holds a card."
```

`board` is a new optional key on `[[workflows]]`. The manifest has no `id` and no `board`
today; `unit` is the join key (`design/agent-model.md:287`), so the key is declared in that
file's schema block: scheduled entries only, the value a board kind, and
`tests/test_workflow_coverage.py` gains `board-join`: for every `board` value, exactly one
entry picks from each column, which is how "one owner, one kind, one runner" (§6) is asserted
rather than remembered. The `agent-proposal` entry gets the same key.
`[surfaces.scheduled].governed_by` and its `notes` name the new runner; `[surfaces.kanban]`
stays retired, because the board is an input to the scheduled surface, not a surface.

Three `[[must_not]]` rows. "Write the card ledger from a scheduled model session", `enforced =
true`, why: the ledger-growth detector discards the run, test:
`tests/test_agent_propose_smoke.sh::ledger-untouched`; the same class as the write-boundary
row. "Approve a brief or decide a card", `enforced = true` since decision 10, why: decisions
exist only in the broker's root-owned stream and derivation reads nothing else, test:
`tests/test_board.py::forged-decision-ignored`. "Write anything but `research.md` on a card
run", `enforced = true`, why: the wrapper discards the run, and only the land step's one note
can merge, test: `tests/test_agent_propose_smoke.sh::card-writes-research-only`.
`bridge_tools` gains `"board"` from day one (decision 7); `bin/fleet_capabilities.py render` turns
it into the shim's `--tools` and the settings deny list, and `check` refuses a hand edit of
either.

`config/fleet-units.tsv` gets `research-brief	system	standing	claudius	timer`, and the
pinned counts move by one: `EXPECTED_TALLY["scheduled"]` 11 to 12 and `LOGICAL_WORKFLOWS` 29
to 30 in `tests/test_receipt_coverage.py`, `STANDING_ENTRIES` 30 to 31 and `LOGICAL_WORKFLOWS`
in `tests/test_control_room_views.py`. The runbook's Job wiring table gets its six-column row.

#### 3.6.6 Skills

S2 gets no new skill. The three pointers Claudius is offered today remain the method skills
for both runs; the mechanism is the profile plus `board.py --help`, on the README's own rule
that a pointer must not duplicate a task profile that owns the same surface
(`tests/test_pointer_skills.sh::no-profile-duplicate`).

S1 gets one vault-owned skill, `08_skills/board-cards/SKILL.md`, written Mac-side (the box
cannot write `main`), with a pointer at `skills/claudius/skills/board-cards/SKILL.md` in the
twelve-line pointer shape (`Canonical source: 08_skills/board-cards/SKILL.md …`, the
description mirrored by `bin/pointer_skills_sync.py`), a fourth entry on the claudius row of
`skills/README.md`'s allocation table, and `"board-cards"` added to every claudius
`[[workflows]]` `skills` list, because `skills-join` demands declared equals offered. The
canonical skill says: the trigger phrases ("put that on the board", "brief this for me",
"what is on my board"); the five tools and what each may do; ask up to three questions before
drafting; check for a duplicate first; take the skeleton from `board_brief` with
`template=true`; close with "card `<id>` waits in Refine"; and the two things the session
never claims, approval and done. Extension to other personas is one canonical skill and one
pointer per owner; if the pointer suite refuses the shared basename across owners, that is a
suite change to take then, not a second skill.

#### 3.6.7 The bridge family (S1, from day one)

`board` joins `FAMILIES` in `buzz-team/buzz-team-mcp.py:43`, declared inline the way
`NOTION_TOOLS` is (qmd is proxied from an external server, the wrong model here):
`board_list`, `board_get`, `board_create`, `board_brief`, `board_note`, each with a JSON
schema for its arguments. Handlers `subprocess.run` the deployed `board.py` with `--actor
"buzz:<agent>"` (the agent from the shim's `--agent` argv, baked in at render time) and, where
the harness exposes one, the turn's interaction id as `--run-id`, so a `note` written from a
conversation joins that turn's interaction receipt. `family_tools()` learns the names so a
persona whose `bridge_tools` withholds the family gets them denied in its settings file.
`tests/test_buzz_team_mcp.py` gets the family over a stub `board.py`: no tool maps to `pick`,
to `edit` or to any decision; a `board_brief` on a card in Todo is refused by the CLI, not by
the shim, so the rule has one home.

#### 3.6.8 Contracts, receipts, sweep

`design/contracts/research-brief.md`, in the eight fixed sections. Identity: unit
`research-brief`, owner claudius, S2, `claude -p --model claude-opus-5`, slug `research-brief`,
alerted, retry idempotent per card and run. Trigger: hourly 08:00-18:00 on weekdays,
`Persistent=false`. Inputs: a Backlog card (absent: `skipped` before the model); the card's
`scope` on the mirror (absent: `DECLINE:` naming the path); `returned` reasons; the mirror,
guarded by `vault_sync_guard.sh check`; the profile and plugin manifest, readable or refuse;
web queries, de-identified per `docs/data_boundary.md`, stated on the `m1-signal-scan`
pattern (§7.1.c).
Outputs: one `brief` event whose text sits at `briefs/<hash>.md`, the receipt's `artifact.uri`
`board://<card>/brief/<hash>`, and the card in Refine; beneficiary Dave; next actor Dave;
benefit signal: the share of briefs approved without an edit, and the return rate, both
countable from the ledger. Decline conditions: the three in the profile. Side effects: the
fleet lock, the attempt log, `cost.log`, one event, one notice line; nothing in git.

Checks: `brief-is-this-run` and `decline-is-this-runs-own` (the polarised pair, exit 77 each
way, as in standing research), `brief-has-all-headings`, `acceptance-has-three-to-five-lines`,
`brief-names-card`, `ledger-untouched-during-model` (the wrapper's
before and after counts, written to the attempt log), `mirror-was-not-dirty`; `when=sweep`:
`timer-fired-this-window`, `not-lock-skipped`. A card left in Refine waits on Dave, not on the
run, so it is the board sweep's `refine-stale`, not a check here. Known failure modes: a brief
that restates the idea (caught by the acceptance-line count, not by prose); a scope path
renamed in the vault (declines loudly); a returned brief re-briefed identically (the CLI
refuses the hash and the run fails its own check).

**Contract environment.** `AGENT_CARD`, `AGENT_CARD_DIR` and `BOARD_ROOT` join
`design/contract-schema.md` § Executor environment and `contract_checks.executor_environment()`:
a check naming an undeclared variable makes the executor refuse the whole run with no receipt
(`contract_exec.py:202-220`), so this is a prerequisite, not a nicety.

`design/contracts/standing-research.md`: the `queue.md` input row becomes "a Todo card,
through `AGENT_BOARD_PICK`; absent: falls through to standing missions and to `DECLINE:`";
the Outputs row gains the card's page. Four checks join, each n/a without a card:
`page-names-card` (the receipt's page carries `$AGENT_CARD`), `published-is-this-run` (the
page's published hash is the hash of this run's `research.md`), `acceptance-answered`
(`research.md` carries one `MET` / `PARTLY` / `NOT MET` line per acceptance line of the brief
the receipt's hash names), `pick-hash-matched` (the wrapper's pick line in the attempt log).
The failure mode "a queue that stopped being regenerated"
becomes "a board with nothing in Todo": a visible decline and an empty column instead of
plausible proposals about the wrong week.

`bin/workflow_receipt.py`: `card` as an optional top-level block on the pattern of `closed`
and `swept` (its own `_card_errors()`: `id` slug-shaped, `workflow` present, `brief_hash` 64
hex or absent, `page` and a 64-hex `page_hash` together or not at all), `None`-tolerant so
every existing receipt still validates, `SCHEMA_VERSION` unchanged. `contract_exec.py` takes
`--card`, `--card-brief-hash`, `--card-page` and `--card-page-hash`; `propose_receipt.py`
passes them from `AGENT_CARD`, the pick's hash and the wrapper's publish.

Sweep: `board.py sweep` on `workflow-receipt-sweep.timer` beside `receipt_sweep.py`. It lands
each new approval (§3.7), fetches canonical `main` for Done, and marks a card's page merged or
rejected. It raises `stale-pick`, `double-return`, `double-changes`, `double-decline`,
`expired`, `refine-stale`, `review-stale`, `land-refused`, `merge-stale` and `forged-decision` as
exceptions in the incident stream, one per card and kind, through a `board` kind in
`bin/workflow_incidents.py`; `refine-stale` fires after three working days in Refine and names
Dave, and `land-refused` an approved text whose hash does not match or a push that failed. It
writes no event, since Done is a join with `main` (§3.7).

#### 3.6.9 The Control Room side, in one paragraph

`systemd/control-room.service.d/board.conf`: `StateDirectory=control-room-board`, the
proposals drop-in's own pattern, which is how a writable root exists under
`ProtectHome=read-only`, and `Environment=CONTROL_ROOM_BOARD_ROOT=/var/lib/control-room-board`.
systemd creates the directory owned by `dave`, which is also the runners' user and, being
user units, the Buzz sessions' user, so the wrappers and the shim write the same root.
`board.py` is imported from the deployed tree the service already runs from
(`ExecStart=/home/dave/agent-workforce/bin/control_room_serve.sh`). The seam `POST
/api/v1/control/board` carries `{verb, card, …}` over the existing shape check, peer gate and
`X-Control-Room: 1` header, and fixes `actor = dave`. It admits exactly the verbs in §3.6.2's
Control Room row: `create`, `brief`, `note` and `edit` go to `board.py`, and decisions go to
the broker. An approval carries what the popup rendered: the brief's hash, and for an artifact
the hash of the page text, which the seam checks against a fresh read before it hands the text
to the broker; an edit carries the card's revision. A stale popup is refused, the proposals
seam's byte-identical rule. Reads join receipts on the `card` block, decisions on the card id,
and `main` for Done; the popup's research section reads the card's page through
`notion_research.py export`, with the Notion token the service reads from
`~/.config/agent-workforce/`. One zod schema, the board page and the card popup (§3.8), rebuilt
through `bin/control_room_build_ui.sh`.

#### 3.6.10 Tests and gates, by name

- `tests/test_board.sh` and `.py`: synthetic cards only, nothing client-shaped; parametrised
  over every column, the two-strike rules (returns, requests for changes, declines), a void pick
  on a failed receipt, a decision naming a brief hash that is not the current one and a pick
  naming one that was never approved, decisions read only from a fixture broker stream (a
  decision-shaped ledger event is `forged-decision` and moves nothing), Done by join against a
  fixture `main`, `land` writing exactly the broker's text as the one note with its front matter
  and refusing a text whose hash is not the signed one, the `edit` rules of §3.8 (refused
  fields, idea and scope voiding the brief, no edit lifting Blocked, the research date holding
  back the pick, a stale revision), actor-verb refusals, idempotent pick per run id, the
  template's headings against `validate-brief`.
- `tests/test_research_brief_smoke.sh`, on the standing-research smoke's shape: env wiring
  (`board` mode, the pick, the verify command); the runner refuses on an unreadable profile
  or plugin manifest; the argv pins `claude-opus-5` literally, offers `WebSearch` and
  `WebFetch`, and puts `--plugin-dir` at `skills/claudius`; the profile keeps `board.py
  template`, the `DECLINE:` sentinel and "never act outward", and names no write verb.
- `tests/test_agent_propose_smoke.sh`: the `board` mode, the receipted skip, the
  ledger-growth `VIOLATION`, `AGENT_RUN_ID` exported once; the card run held to `research.md`
  (`card-writes-research-only`) and published through a stubbed `notion_research.py`, with no
  git in the run.
- `tests/test_notion_research.py`: export is deterministic for the same blocks, publish is
  idempotent per card and run, and the token reaches neither argv nor a log.
- `tests/test_propose_receipt.py`: `BOARD` to `--artifact board://…`, `--card` passthrough,
  the card's page and its hash. `tests/test_contract_exec.py` and `test_contract_schema.py`: the
  three environment names.
- `tests/test_receipt_coverage.py`, `test_control_room_views.py`: the counts.
  `tests/test_fleet_ownership.sh`: the tsv row and the `Owner:` line.
  `tests/test_workflow_coverage.py`: `board-join`, and `skills-join` with the new pointer.
- `tests/test_pointer_skills.sh`: the README row, the pointer's twelve lines, the target's
  existence on the box. `tests/test_buzz_team_mcp.py`, `test_fleet_capabilities.sh`: the
  family and its rendering. `tests/test_buzz_unit_wiring.sh`: the producer row.
- `tests/test_control_room_api.py`, `test_control_room_spa.sh`: the seam, `edit` included, the
  read model, the rebuild stamp. `CardDialog.test.tsx` beside the popup, parametrised over the
  seven columns: the fields each column unlocks and the buttons it offers, as the read model
  states them; a refused stale save that reloads; the unsaved-edit guard on close; a research
  date after the deadline refused.
- `tests/test_control_broker.py` and `.sh`, for the seven decision verbs and the signature.
  `tests/test_agent_inbox_branch_rows.py`, for the skipped `card-` branch. Vault-side,
  `agent_branch_test.py`, for `merge --expect-sha`, the one-note check and the body hash (I10,
  on the Mac).
- `bin/check_deploy_drift.sh` stays red until `bin/deploy` ships the new scripts, profile and
  units; `tests/ci-expected-skips.txt` takes the box-gated lines.
  `tests/test_instruction_size.sh`: the one bullet the board earns in CLAUDE.md under Research
  pipeline jobs must fit the ceiling that only goes down.

#### 3.6.11 Provenance, stated plainly

Every process that can reach the ledger runs as `dave`: `control-room.service` (`User=dave`),
the scheduled runners (`User=dave`), the Buzz units (user scope). The ledger cannot tell
writers apart by credential, and since decision 10 it no longer has to: nothing that moves a
card past a gate is a ledger event. Dave's decisions live in the broker's root-owned stream,
signed with a key only root can read. The two writes that matter are checked off the box. A
card's research reaches canonical only as the App, which `main` refuses server-side, and only
as the text Dave approved, from the broker's copy. The Mac merges only a decision whose
signature checks, and only a branch whose one note hashes to what it signs (§3.7). The card's
Notion page is trusted by nothing after an approval, since anything holding the box's Notion
token can edit it. Two things stay provenance, not proof. One is the actor on a ledger event
(`create`, `brief`, `note`, `picked`). The other is whether a decision came from Dave's hand or
from Claude in a Mac session calling the seam as Dave (gap 1, §7.2, accepted for the pilot). If
it comes to matter, the mechanism is a step-up check on the decision verbs: a WebAuthn touch in
the browser, which needs the Control Room on HTTPS.

#### 3.6.12 Files that appear or change

| File | New or changed | Owns |
|---|---|---|
| `bin/board.py`, `tests/test_board.*` | new | the ledger, derivation, CLI, template, `land` |
| `bin/agent_propose.sh`, `tests/test_agent_propose_smoke.sh` | changed | run id, pick, `board` mode, the card run's publish, the detector |
| `bin/notion_research.py`, `tests/test_notion_research.py`; the Research database's id in `~/.config/agent-workforce/`, set up by hand | new | the card pages: publish, export, mark |
| `bin/agent_inbox_branch_rows.py` | changed | skips `card-` branches, so no card gets an Agent Inbox row |
| `bin/run_research_brief_cc.sh`, `bin/brief_or_decline.sh` | new | the brief run's argv and its verify contract |
| `profiles/research_brief_cc_task.md`, `profiles/research_brief.env.example` | new | the agent's workflow for briefing |
| `profiles/standing_research_cc_task.md`, `profiles/standing_research.env.example` | changed | the card as tasking; `research.md` with the acceptance answers |
| `systemd/research-brief.{timer,service}`, `config/fleet-units.tsv`, `bin/buzz_producers.tsv`, `docs/runbook.md` | new rows | wiring |
| `design/agents/claudius.toml`, `design/agent-model.md` | changed | the entry, the `board` key, three `must_not` rows |
| `design/contracts/research-brief.md`, `design/contracts/standing-research.md`, `design/contract-schema.md` | new / changed | checks and the executor environment |
| `bin/workflow_receipt.py`, `bin/contract_exec.py`, `bin/propose_receipt.py`, `bin/contract_checks.py` | changed | the `card` block, `BOARD`, the environment names |
| `bin/workflow_incidents.py`, `bin/receipt_sweep.py` (or a sibling call) | changed | the board sweep and its exceptions |
| `bin/control_room_api.py`, `bin/control_room_state.py`, `ui/control-room/src/*`, `systemd/control-room.service.d/board.conf` | changed / new | the seam, the read model, the board page and the card popup, the state root |
| `bin/control_broker.py` (the source of the root copy), `bin/control_broker_allowlist.py`, `tests/test_control_broker.*`; the signing key under `/etc/control-room/` and the stream under `/var/lib/control-room/receipts/board/`, installed by hand | changed / new | the seven decisions, signed (I9) |
| `skills/README.md`, `skills/claudius/skills/board-cards/SKILL.md`, vault `08_skills/board-cards/SKILL.md` | new | the S1 skill (from day one) |
| `buzz-team/buzz-team-mcp.py`, `bin/fleet_capabilities.py`, `tests/test_buzz_team_mcp.py` | changed | the `board` family (from day one) |
| vault `00_system/tools/agent_merge_watch.sh`, `agent_branch.py`, `agent_branch_test.py`, the broker's public key; `00_system/vault_map.md`, `05_knowledge/research/`, qmd's folder context (Mac and box) | changed / new, Mac-side | the watcher's board pass and the research area (I10) |
| `CLAUDE.md` (one bullet), `tests/test_standing_research_smoke.sh`, `04_operations/box_brief/queue.md` (vault) | changed | succession of `queue.md` (decision 2) |

### 3.7 Draft, decide, apply (added 2026-09-28; revised 2026-10-06)

Dave asked why he had to decide in Notion rather than on the board, and pasted in an outside
review of the question. The review frames it the professional way: keep three planes apart.
Agents **draft** where nothing trusts the draft. A human **decides** in one queue. A different
identity, one no agent can satisfy, **applies** the decision to the store of record. It asks
for five things, and each is adopted here:

- Approve, Edit and Reject on In Review, through the broker.
- An Approve that queues the apply, instead of a reminder to promote later.
- A mechanical Mac step: a clean approval lands with no terminal, and a conflict stays on the
  card.
- No deciding card work in Notion.
- No writing to canonical first and reverting later.

Dave settled the rest on 2026-10-06 (decisions 11-16). The research is a page in a new Notion
Research database. He decides on the board and nowhere else, and may edit the page before he
approves it. What he approves is copied into a research area of the vault, kept apart from his
own notes. **One approval:** his click on the board is the only human step between a finished
run and the vault. Everything after it, the signature included, is machinery (decision 12).

**The vault already runs the three planes for agent branches (§2).** This note's first drafts
built the research artifact on the retiring inbox path. That path has no apply step, which is
why deciding looked like one click in Notion and a second one at the Mac.

| Plane | The branch path today | What the board does |
|---|---|---|
| Draft | file edits at real vault paths on `agents/<date>-<slug>`, pushed as the App, which `main` refuses | the research run writes one file, and the wrapper publishes it as the card's page in the Notion Research database (decision 11) |
| Decide | a Notion Agent Inbox row set to Approved or Rejected | the card: Approve, Request changes, Reject, each a signed broker decision (decisions 10 and 12); an approval takes the page as it stands (decision 16) |
| Apply | `agent_merge_watch.sh` on the Mac, hourly: a headless `claude -p` maps Approved rows to branches, and `agent_branch.py merge` lands the clean single-target ones | the box lands the approved text as one new note on `agents/<date>-card-<id>`; a model-free pass on the Mac verifies it and merges |

**Why the apply pass must be model-free.** Read on 2026-09-28 from the watcher's log
(`~/.claude/logs/agent-merge-watch.log`), its script and `main`'s feed. The feed,
`04_operations/box_brief/approvals.tsv`, holds eight decisions since the branch path began, and
the last is dated 2026-09-01. Since then the watcher has started a model pass 187 times, from
2026-09-11 on, and none merged anything:

- 136 could not read Notion. The claude.ai connector needs re-authorizing, which a headless
  session cannot do.
- 36 found only Approved rows naming inbox files on the box-safe mirror, which have no branch
  to merge.
- 15 did nothing else: ten found nothing to do, four stopped on a session limit or an
  unreachable API, and one gave no reason.

The script then classifies each pass by grepping the model's prose, and that fails open. It
tests for `NOTHING APPROVED` first, and a model writing that it did not report "NOTHING
APPROVED", because it could not check, matches that test. So 42 Notion failures were logged as
quiet no-ops, with no notice. Prose without an escalation word falls through to "merge pass
completed", which notifies that branches merged: 16 times, with no merge. The guards in
`agent_branch.py` were never the problem. A board decision names its card and the hash of the
text it approves, and needs neither a connector nor a reading of prose, so the board pass can
be a script.

**Draft: the card's page** (§3.6.3, item 5). The research run writes one file, `research.md`:
the findings, then each acceptance line of the brief answered `MET` / `PARTLY` / `NOT MET` with
the finding it rests on, then the sources. After a request for changes the wrapper first
exports the current page, Dave's edits included, to `research.prev.md`, so the run revises
rather than starts over. After the model exits, the wrapper publishes the file through
`bin/notion_research.py` as the card's page: one page per card, created by the first run and
rewritten by the next, with Notion's page history keeping each version. The page carries the
card id, the title, a link back to the card, the run and its version, and later the vault
note's path. The agent never holds a Notion credential and never calls Notion; the wrapper
does, as the daily jobs reach Notion only through `bin/notion_daily.py`. The receipt's `card`
block records the page and the hash of what was published. Card-less standing research keeps
today's inbox path until the fleet cutover.

**Decide: three verbs on In Review.** The popup renders the page as it stands when the popup
opens, read through `notion_research.py export`, beside the brief's acceptance lines and their
answers, with a link to open it in Notion and a mark when it changed since the run published
it. Dave may edit the page in Notion first (decision 16).

- **Approve** carries the hash of the text the popup rendered. The seam reads the page again
  and refuses if it changed, and the popup reloads: the rule the brief approval and the edit
  revision already follow. Otherwise it hands the text to the broker, which keeps it beside the
  signed decision in its root-owned stream. What lands is exactly what Dave saw, whatever
  happens to the page afterwards.
- **Request changes** is the review's "Edit". It carries Dave's note and returns the card to
  Todo, and the next run revises the same page. Two requests for changes block the card, by
  the two-strike rule.
- **Reject** carries a reason and closes the card into Done with the outcome `rejected`
  (decision 13). Nothing reaches the vault, and the sweep marks the page rejected.

All three are broker decisions (decision 10). No card ever gets an Agent Inbox row, so the
board is its only decision surface.

**Apply: land on the box, merge on the Mac.** Two model-free steps, one on each side of the
membrane:

1. **Land.** `board.py land`, run by the sweep, takes each approval it has not landed. It reads
   the approved text from the broker's stream, checks it against the signed hash, and writes it
   as one new note, `05_knowledge/research/<id>.md` with the front matter below, on
   `agents/<date>-card-<id>`, cut from a freshly fetched `origin/main` in a worktree of the
   canonical clone. It pushes as the App and removes the worktree. The text is the broker's
   copy, never the page and never the run's file.
2. **Merge.** The watcher's board pass, added to `agent_merge_watch.sh` ahead of its Notion
   pass, fetches unapplied approvals from `GET /api/v1/board/decisions` and checks each
   signature against the broker's public key, pinned on the Mac at install (decision 12). It
   merges only when all four hold:
   - the branch adds exactly one file, the note for the card the decision names, and changes
     nothing else: no edit, no rename, no delete;
   - the note's body, below its front matter, hashes to what the decision signs;
   - the branch tip is the commit it checked;
   - `agent_branch.py merge --expect-sha` finds no conflict and no new lint violation.

Anything else escalates the way the watcher already does: nothing lands, the Mac notifies, and
the card stays In Review, badged. An approval still unmerged two watcher cycles later is
`merge-stale`, naming Dave. The Mac is the only apply identity, so nothing lands while it
sleeps. A rejected card never had a branch, so there is nothing to delete.

**Where research lives in the vault (decision 15).** One note per approved card,
`05_knowledge/research/<id>.md`, beside `raw/`. A card only ever adds its own note and never
edits Dave's notes, so folding a finding into them stays his act, and no two cards can clash
over a file. Every note opens with the same front matter, written by the land step:

```yaml
type: research
card: <id>
title: <the card's title>
question: <the brief's research question>
tags: [<the card's tags>]
approved: <date>
notion: <the page's URL>
run: <run id>
brief: <the approved brief's hash>
content: <the approved text's hash>
```

Retrieval rides on that shape, with no index file to keep in step:

- qmd already indexes `05_knowledge/`, on the Mac and on the box. The folder gets its own
  `context` line in qmd's `index.yml` on both ("agent research, one note per card, approved by
  Dave on the board"), so every hit says what it is.
- Obsidian's property search, and an agent's `qmd` or `grep`, filter on `type: research`,
  `card` or `tags`.
- `00_system/vault_map.md` names the folder under `05_knowledge/`.
- A Done card links to its note and its page, and the sweep writes the note's path onto the
  page once it is on `main`.

**Done is read from `main`, which only Dave writes.** An approved card is Done when its note is
on `origin/main` in the box's canonical clone with the approved hash, or when `main`'s feed
records `merged` for its branch. No box credential can write either. Three things retire with
this: the `decided` event; the sweep's write through a broker it could not reach; and the old
reliance on an `approvals.tsv` under `_inbox/agents/`, inside the research runs' own write
boundary (gap 2, §7.2).

**Why a board decision is stronger than the Notion status it replaces.** The Notion pass acts
on a Status value the box's own sync token can set: the token `bin/agent_inbox_apply.py` uses
to PATCH those same rows. A board decision exists only in the broker's root-owned stream,
signed with a key only root can read. No process running as `dave` can write the stream, read
the key, or produce a signature the Mac accepts, however the record travels. A token like that
can also edit a card's page, which is why nothing after an approval reads the page: the land
step writes the broker's copy.

**What an agent may write, by zone.** The review's tiers, applied to this board:

| Zone | Here | An agent may |
|---|---|---|
| Scratch | `runs/<run_id>/` | write directly |
| Co-authored record | the card ledger; the card's Notion page | the ledger through `board.py` only: the wrapper in a scheduled run (§3.6.3's detector), the bridge family in a Buzz session (§3.6.7); the page only through the wrapper's publish |
| Canonical knowledge | `05_knowledge/research/<id>.md` | nothing directly: Dave approves, the box lands his approved text, the Mac applies |
| The rest of the vault | anywhere | never, from a card |

The review also lists daily captures as a zone agents write directly. The fleet's rule is the
opposite: the daily jobs never write `07_daily/` (CLAUDE.md § Daily rhythm jobs). A fleet-wide
tier policy is a vault-contract decision, and it is not taken here.

### 3.8 The card popup (added 2026-09-28)

Dave asked to open a card from the board, see its detail and edit it, in a popup inside the
Control Room. The card page of the earlier drafts becomes that popup: a `CardDialog` on the
SPA's own `DialogFrame` (`ui/control-room/src/components/dialogs/DialogFrame.tsx`), opened over
the board at the frame's existing `wide` width. The frame gains one optional prop, a header
slot: its `title` is a plain string today, and the popup's title is an input with the column,
the schedule and the id under it. Opening a card sets the URL to `/app/board/<id>`, a new route
beside `/app/board` in `router/routes.ts`, so a Buzz notice or a run page can link straight to
it; closing returns to the board. Creating a card opens the same popup, empty.

**Layout: the mockup Dave approved on 2026-10-06.** The mockup is
[`agent-board-card-popup-mockup-2026-10-06.html`](agent-board-card-popup-mockup-2026-10-06.html),
beside this note, drawn in the Control Room's own colours, inputs and buttons. It shows a card
in Todo:

```text
+--------------------------------------------------------------------------+
| [Vector search options for the vault]                                [x] |
| (Todo) (Scheduled Tue 6 Oct)  vault-vector-search                        |
+-----------------------------------------------+--------------------------+
| Brief         v2 by Claudius, approved 28 Sep | Research date            |
| +-------------------------------------------+ | [2026-10-06]             |
| | ## Do                                     | | Not before this          |
| | Compare three local vector search options | | morning's run            |
| | ## Acceptance ...                         | |                          |
| | ## Sources ...                            | | Deadline                 |
| +-------------------------------------------+ | [2026-10-16]             |
| [Save] [Save and approve]                     |                          |
| A changed brief goes back to Refine           | Priority      [High  v]  |
|                                               | Tags  (search) (tooling) |
| Idea                                          |                          |
| [Can the vault search run locally ...]        | Scope                    |
|                                               | [vault:05_knowledge]     |
| Activity                                      | Until the first run;     |
| Mon 28 Sep  Brief approved by Dave            | re-briefs                |
| Mon 28 Sep  Brief v2 by Claudius              | ------------------------ |
| Fri 25 Sep  Returned by Dave: keep it local   | Owner   Claudius, locked |
| ...                                           | Kind    Research, locked |
| [Add a note                          ] [Add]  |                          |
+-----------------------------------------------+--------------------------+
| Moves by decision only                                [Block] [Withdraw] |
+--------------------------------------------------------------------------+
```

- **Header.** The title, editable. Under it the column, the research date as "Scheduled" while
  the card waits for it, and the id. The column carries its state where it has one: a Blocked
  card names its cause, and an approved card in In Review says it lands within the hour (§3.2).
- **Body**, top to bottom:
  - the brief, with its version, who wrote it, and whether the text on screen is the approved
    one. Its Save and Save and approve buttons work only once the text has changed;
  - the idea;
  - once a run has published, the research: the card's Notion page as it stands, read when the
    popup opens, with a link to open it in Notion and a mark when it changed since the run
    published it, and each acceptance line beside its `MET` / `PARTLY` / `NOT MET` answer
    (§3.7);
  - the activity, newest first: every event, decision and run, each run linked to its receipt,
    with a box to add a note.
- **Side panel.** Research date, deadline, priority, tags and scope, each with a one-line hint
  where its rule is not obvious; below a rule, owner and kind, locked.
- **Footer.** "Moves by decision only" on the left; on the right, the buttons the column
  allows (the moves table below), with Withdraw in the danger style.
- A field the column does not allow shows as text, with the reason as its hint. On a narrow
  screen the side panel moves under the body. Closing with unsaved edits asks first, whether by
  the close button, Escape or a click outside, since `DialogFrame` closes on all three.

The other columns differ from the mockup only in the fields the table below unlocks, the moves
table's buttons and, from In Review on, the research section.

**What can be changed, and when.** Every change is an `edited` event written by `board.py
edit`, so the history keeps the old value.

| Field | Editable in | Effect |
|---|---|---|
| title, tags, priority | every column but Done | none beyond the label; priority orders Todo |
| research date (`research_on`, new) | every column but In Progress and Done | the 04:30 pick passes over the card before that date; Todo shows it as scheduled |
| deadline | every column but In Progress and Done | past it, the card is Blocked; on a Blocked card the popup saves the new date together with Unblock |
| brief | Backlog, Refine, Todo, Blocked | a new version, a `brief` event by `dave`; an approved brief goes back to Refine, unless Dave chooses "Save and approve", which adds the broker's approval of the new hash |
| idea, scope | Backlog, Refine, Todo, Blocked, until the first research run | with a brief on the card, back to Backlog for a new brief, since the brief was written for the old idea and scope |
| notes | every column | appended, never edited or deleted |
| owner, kind | nowhere in the pilot | Claudius is the only research owner; another kind is another card |
| id | nowhere | it names the page, the note, the branch and the receipts |

The column, the research output and the history are not fields. The output changes through
Request changes, or on the Mac. Runs, receipts and decisions are the record.

**Two dates, two meanings.** The research date means "not before" (decision 14). The research
run takes one card each weekday at 04:30, so a card dated Tuesday runs on Tuesday if it is the
highest priority waiting, and otherwise on the next weekday. The deadline means "by when": past
it, the card stops (§3.2). A research date after the deadline is refused at save.

**Moves.** The column is never edited and never dragged. A card moves only by a decision, and
the footer offers only the ones its column allows:

| Column | Buttons |
|---|---|
| Backlog | Withdraw |
| Refine | Approve brief, Return with a reason, Withdraw |
| Todo | Block, Withdraw |
| In Progress | none |
| In Review | Approve, Request changes, Reject |
| Blocked | Unblock, Withdraw |
| Done | none |

Withdraw is Reject outside In Review: the same broker `rejected` decision with a reason, shown
as `withdrawn`, so the broker keeps its seven verbs. A withdrawn card closes like a rejected
one: nothing reaches the vault, and a page it already has is marked withdrawn.

**Rules that keep the gates where they are.**

- `edit` is a ledger verb, not a broker verb, because an edit only moves a card backwards: a
  new brief, idea or scope voids an approval. Nothing an edit writes approves, unblocks or
  closes a card. Blocked is lifted only by `unblocked`, whatever the deadline now says.
- The Control Room and the Mac seam may call `edit`. The runners and the bridge family may not,
  and `board.py` refuses their actors, so an agent never reorders or reschedules its own queue.
- Every save carries the card revision the popup rendered, and `board.py` refuses a stale one,
  the proposals seam's rule. If the brief run posted a new version while the popup was open,
  the save is refused and the popup reloads.
- A card does not change under a running run. While a card is In Progress, only title, tags,
  priority and notes save.
- One copy of the two tables. The read model carries, per card, the fields its column allows
  and the moves it offers, computed by `board.py` from the same tables that refuse an edit. The
  popup renders them and keeps no copy, so the screen and the refusal cannot drift.

## 4. What S3 taught, as rules the pilot must satisfy

| S3 measurement | Rule | Mechanism |
|---|---|---|
| 5 cards assigned to a profile not on disk | a card cannot be created with an owner that has no runner for its kind | `board.py create` validates against `design/agents/*.toml` and the runner table |
| 0 of 6 done cards carried a result | Done is derived from a merge or a rejection, never written by an agent; every worked card carries an approved acceptance bar the artifact answers | Done only from `main`, which no box credential can write, or from the broker's `rejected`; no `done` verb exists; `brief_approved` pins the hash; a contract check that `research.md` answers each acceptance line |
| 0 of 11 used `skills` | no per-card capability fields | skills stay on the manifest |
| LLM polled every 60 s; same-day phantoms | no LLM poller: the brief timer's quiet tick is a receipted skip before any model starts; pick is idempotent per run id | `AGENT_BOARD_REQUIRED` (§3.6.3); `picked` keyed on `AGENT_RUN_ID` |
| 44 days idle, nobody looked | the board is the input to a standing job and is rendered where Dave already looks | Control Room page; an empty Todo column shows as a decline, not silence |
| card bodies are client content | nothing card-shaped in the public repo | state root outside git; synthetic fixtures only |

## 5. Extension to dev cards, and what is missing today

The lifecycle Dave wants maps onto pieces that exist on the Mac and personas that exist on the
box:

| Stage | Today (Mac) | On the board |
|---|---|---|
| ideation, description | Dave + Claude in a session | Backlog card, `kind = dev` |
| design, architecture, plan | `plan-feature` writes a brief | Refine: the plan is the card's brief, written by Trajan's brief run |
| plan approval | Dave reads the brief | `brief_approved`, the same broker decision and gate as a research card |
| build, test | `implement`, `finish` | Trajan's run on the card's `scope` worktree, a branch named for the id |
| verify, review | `ship-dev-plan`'s independent verify + review | Aurelian: cold verification, never a co-author, read-only by manifest |
| merge | Dave | Approve on In Review, as for research; Done derives from the merge |

Four things to settle before that phase, none of them in the pilot:

1. **Trajan has no headless runner.** His `[surfaces.scheduled]` is `present = false`; his
   fourteen standing jobs are platform timers, not Claude runs, and his only model surface is
   Buzz. A build card needs an S2 wrapper for Trajan (`run_dev_card_cc.sh` on the m1 pattern)
   or the S4 route (a timer wakes his Buzz session and waits), which T7.2 shows is the fragile
   one. The S2 wrapper is the smaller, receipted change.
2. **Aurelian verifies from a Buzz session that may not write files.** Verification output
   must arrive as a delivery or an event, not an edit; the T5.3d handoff-trace fields on the
   receipt are the place for a Trajan → Aurelian handoff.
3. **The Dev Plan decision.** The 2026-09-10 review fixed "the Dev Plan stays the only
   delivery backlog", and the September plan closed its scope on 2026-09-18 with new work
   living in its own tracker. A research board does not collide with that. A dev board is a
   delivery backlog and does; that decision is re-taken when dev cards arrive, not quietly
   overridden.
4. **`scope` becomes enforcement.** For dev cards the writable worktree is the card's `scope`
   and nothing else; the podman brief's per-agent mount manifest is the natural home for that
   rule once containers land.

The T8.7 measurements (first pass, rework, plan fidelity) become per-card numbers for free once
the land record names the card.

## 6. Non-goals for the pilot

- No Agent Inbox row for a card, and no decision taken in Notion. A card's one Notion presence
  is its page in the Research database, which holds the research and no status anyone decides
  on; the board reads the page's text from Notion and nothing else. The Agent Inbox stays the
  decision surface for branches and proposals no card owns, and the Content DB stays
  Augustus's. The review suggested a one-way board-to-Notion mirror of the card; it is left
  out, because a mirrored row looks decidable and the watcher's Notion pass acts on any
  Approved row it finds.
- No second approval. Dave's click on the board is the only human step between a finished run
  and the vault (decision 12).
- No edits to Dave's own notes from a card. A card adds its one note in `05_knowledge/research/`;
  folding a finding into his notes stays his act (decision 15).
- No write-then-revert into canonical. A card's work reaches `main` only after Dave's decision,
  through the Mac. A wrong note on `main` is cited by every later run until someone notices.
- No LLM poller. The brief timer is model-free on a quiet tick; the research dispatch stays
  04:30.
- No per-card model, tool or skill overrides.
- No S3-style generic "assign a card to any agent": one owner, one kind, one runner.
- No silent brief edits after approval: a changed brief voids the approval and returns the
  card to Refine, unless Dave approves the new version in the same save (§3.8).

## 7. Decisions for Dave — 1-10 resolved 2026-09-26 (4 revised 2026-09-28); 11-16 resolved 2026-10-06

1. **Store.** (a) box-native ledger under a state root, read through the API (recommended:
   survives the vault cutover, private by default, one host for derivation); (b) a Notion DB
   on the Augustus pattern; (c) files on the `agents/inbox` branch under `_inbox/agents/`
   (inside the write boundary, but the mirror it lives on is slated for retirement).
   **→ Decided: (a).** No delta; §3.4 and §3.6.9 stand as designed.
2. **Succession.** The board replaces `queue.md` for research tasking (recommended), or runs
   beside it for a period. Beside means two backlogs and the S3 idle-board failure again.
   **→ Decided: replaces `queue.md`.** No delta; I7 (§8) stands.
3. **Columns.** The Dev Plan's seven, Backlog / Refine / Todo / In Progress / In Review /
   Done / Blocked (recommended: one vocabulary for research and dev cards, each column waiting
   on one actor), or the first draft's six with the brief gate shown as a badge inside Backlog.
   **→ Decided: the seven.** No delta; §3.2's table stands.
4. **Where Dave decides on a research artifact.** Stay in the Notion Agent Inbox and the Mac's
   promote tool, with Done derived (recommended), or move promote / reject onto the board,
   which would give the box a write path into the vault's approval record it does not have.
   **→ Decided 2026-09-26: stays in Notion. Revised 2026-09-28: on the board.** The reason
   given for Notion was wrong: the box already writes the approval record, since
   `bin/agent_inbox_apply.py` applies every Notion rejection itself. Dave asked why he could
   not decide on the board, and an outside review answered: keep draft, decide and apply
   apart, and move the decision onto the card. See §3.7 and §7.1.e.
5. **Dispatch for the pilot.** Research stays on the 04:30 weekday timer (recommended). The
   brief step: an hourly weekday timer with a model-free pre-flight (recommended), a systemd
   `.path` unit on the ledger (immediate; the repo's first path unit), or folded into the 04:30
   run (rejected in §3.2a).
   **→ Decided: hourly pre-flight timer.** Delta, applied 2026-09-28: §3.6.3's timer, §3.6.5's
   `trigger` and §3.6.8's contract said every two hours, and now say hourly.
6. **Agent instructions.** Profile section plus `board.py --help` for S2, vault-owned skill
   plus pointer for S1 (recommended), or a repo-owned mechanism skill, which the pointer-skill
   suite currently refuses.
   **→ Decided: profile + pointer skill**, checked against Anthropic's "AI-native SDLC"
   playbook (`https://claude.com/blog/the-ai-native-sdlc-playbook`, fetched 2026-09-26). See
   §7.1.a — the design already matches it; one tension named, nothing changed.
7. **S1 in the pilot.** Card and brief drafting from a Buzz conversation with Claudius is in
   (adds the bridge family, one more brief) or deferred to the second slice (recommended: the
   async path must exist first). The conversational brief, where Claudius asks before he
   drafts, is the strongest reason to do S1 at all.
   **→ Decided: in, from day one.** Dave: the prerequisite this was waiting on — reliable `@`
   addressing to an agent inside Buzz desktop — already shipped, separately from this board.
   See §7.1.b.
8. **Card creation from the Mac.** The Control Room page only, or also the seam over the
   tailnet for Claude on the Mac. The seam costs nothing extra once the page exists.
   **→ Decided: also the seam.** No delta; §3.3 already assumed it.
9. **Brief run tools.** Corpus only, Read / Grep / qmd over `scope` (recommended: cheap, fast,
   and the web belongs to the run Dave approved), or with `WebSearch` / `WebFetch` for a
   landscape check before the brief.
   **→ Decided: with web tools.** See §7.1.c.
10. **Approval-class verbs.** Rule plus detector in the pilot (recommended: every writer on the
    box is `dave`, so the ledger cannot prove an actor either way, and the Mac-side gates bound
    the blast radius), or behind the root-owned broker from day one (§3.6.11: three more
    allowlist verbs and a root-owned human-touch stream, hand-installed like the broker).
    **→ Decided: behind the broker, from day one.** See §7.1.d.
11. **The card's research artifact** (new, from the 2026-09-28 review). A branch on canonical,
    `agents/<date>-card-<id>`, holding edits at the brief's target paths, merged by the Mac
    watcher after Dave approves on the board (recommended: it is the vault's own ratified write
    path, and the only one with a mechanical apply). Card-less standing research stays on the
    inbox until the fleet cutover (migration runbook §6-§8). Or an inbox file as today,
    decided on the board and promoted by hand on the Mac with `agent_inbox.py`, with no
    mechanical apply.
    **→ Decided 2026-10-06: a Notion page, decided on the board, then copied into the vault.**
    Neither option as written. Dave: "the notion page is the artifact"; approving happens on the
    board, not in the Agent Inbox. Follow-ups, same day: the pages live in a new Notion Research
    database, one page per card; after approval the research also goes into the vault, in an
    area kept apart from curated knowledge and easy to retrieve (decision 15). §3.7's draft step
    changes from a branch to the page; its apply step, an `agents/*` branch the Mac watcher
    merges, stays.
12. **How the Mac trusts a board decision** (new). The broker signs each decision with a
    root-only key, and the watcher checks it against a public key pinned on the Mac
    (recommended: nothing running as `dave` can forge one, however it travels). Or the watcher
    trusts the Control Room API over the tailnet, where a process running as `dave` can stop
    the service and answer on its port.
    **→ Decided 2026-10-06: the broker signs, the Mac checks.** Dave: no approval step beyond
    his click on the board. Neither option added one; the signature is made and checked by
    machines behind the click. It is needed because the Mac acts on every approval: approved
    research is copied into the vault (decision 11).
13. **Where a rejected card goes** (new; closes gap 3, §7.2). Into Done, with its outcome shown
    as `rejected` (recommended: it waits on nobody, which is Done's test, and the seven stay the
    Dev Plan's), or an eighth column, Rejected. A card withdrawn before review (§3.8) goes the
    same way.
    **→ Decided 2026-10-06: into Done, marked rejected.**
14. **What the research date means** (new, from the card popup, §3.8). "Not before"
    (recommended): the research run still takes one card each weekday at 04:30, highest
    priority first, so a card dated Tuesday runs that Tuesday if it leads the queue, and
    otherwise on the next weekday. A failed or skipped run leaves the card to the next morning.
    Or "on that day": two cards can share a date, so this needs either more than one card per
    run or a date picker that refuses a weekday another card holds, and a card whose run failed
    waits for Dave to give it a new date.
    **→ Decided 2026-10-06: not before.**
15. **Where approved research lives in the vault** (new, 2026-10-06, from decision 11). In
    `05_knowledge/research/`, one new note per card with a fixed front matter, never an edit to
    Dave's own notes (recommended: research kept apart and filterable, and no two cards can
    clash over a file); or a new top-level folder; or, as the branch design had it, edits to
    the notes the brief names.
    **→ Decided 2026-10-06: `05_knowledge/research/`.** Dave asked for research kept apart and
    easy to retrieve; §3.7 says how.
16. **Whether Dave may edit the page before approving** (new, 2026-10-06). Yes: he approves the
    page as it stands, and that text is what lands (recommended: a small fix costs no rerun);
    or no, every change goes through Request changes and a rerun.
    **→ Decided 2026-10-06: yes.**

### 7.1 Deltas from the decided answers

Three of ten departed from this note's recommendation, and decision 4 was revised on
2026-09-28. The deltas were applied into §3, §3.6 and §8 on 2026-09-28; they stay here as the
record of what each decision changed.

**a. Decision 6 — checked against Anthropic's AI-native SDLC playbook.** Its three relevant
claims, and how this design already sits against them:

- *"Each stage ends by writing one [artifact] to version control … the next stage begins by
  reading it."* The brief already is that artifact (§3.2a): drafted, frozen by hash, read by
  the next stage. It is not committed to **git** — §2 already rules that out for client-derived
  content in this public repo — but the append-only, hashed ledger under
  `/var/lib/control-room-board` (decision 1) is the same durable trail in spirit, on the
  reasoning receipts and `_inbox/agents/` already use. No design change; naming this now so it
  is not reopened later. Since §3.7 the research artifact itself is in version control too, as
  a branch in the private vault repo.
- *"Hooks are the approval gates … enforced every time, for everyone."* This is the argument
  for decision 10, not 6 — the ledger-growth detector (§3.6.3.4) is already such a hook for the
  write boundary; the broker extends the same posture to the approval verbs.
- *"The agent may act up to the production gate and cannot pass it."* Already the design: the
  merge into `main` stays Mac-side, and `main` refuses the box's only credential server-side
  (§3.7).

No change to §3.6.4 or §3.6.6.

**b. Decision 7 — S1 moves out of "second slice."** §3.6.7 (the bridge family) and the S1
skill in §3.6.6 are no longer gated behind "if decision 7 is yes"; they are initial scope. In
§8, I8 loses that qualifier: it depended only on I1 before and still does, so it now builds
alongside I2/I3 rather than after them. Nothing in §3.6.7's design changes — the fix Dave named
(reliable `@agent` addressing in Buzz desktop) resolved a transport problem this note never
modeled; the bridge family and the vault skill were always going to need building regardless.

**c. Decision 9 — the brief run gets web tools.** Applied 2026-09-28 at every site that said
otherwise:
- §3.2a's description of the run.
- §3.5 step 2.
- §3.6.2's brief-run row.
- §3.6.3's `--allowedTools`.
- §3.6.4's step 1, which gains the landscape check, and step 4.
- §3.6.5's `web` key.
- §3.6.8's check list, which drops `no-web-tools-offered`.
- §3.6.10's smoke test, which now asserts both tools are offered.

The first cut of this delta named four of those eight sites. No new contract check replaces
`no-web-tools-offered`. `design/contracts/m1-signal-scan.md` (read 2026-09-26), one of the two
jobs that had web tools until now, standing research the other, states its de-identification
discipline as an **Inputs-section property, not a mechanized check**: *"This is one of two jobs
in the fleet with web tools in its allowlist … De-identification therefore applies to what it
sends: queries and fetched URLs leave the bubble"* — resting on `docs/data_boundary.md`'s rule
and the profile's own wording, never on an automated check. The brief run becomes the **third**
such job and inherits the identical, already-unenforced-by-check posture: one more line in
`research-brief.md`'s Inputs section, on the m1-signal-scan pattern.

**d. Decision 10 — Dave's decisions go through the broker from day one.** §3.6.11's "if it
ever matters" branch is now the design:
- Every verb only Dave may take is a broker verb. That is approving or returning a brief;
  approving, requesting changes on or rejecting an artifact; and blocking and unblocking. They
  are allowlisted in `/etc/control-room/allowlist.json` (rendered by
  `bin/control_broker_allowlist.py`) and executed by the root-owned
  `/usr/local/lib/control-room/control_broker.py`, files CLAUDE.md already names as
  hand-installed and outside `bin/deploy`'s reach. The first cut of this delta named only
  `approve`, `decided` and `block`, and left `return` and `unblock` as an open question. The
  review's shape settles it: a verb only Dave may take is a broker verb. `decided` is gone,
  since Done is read from `main` (§3.7).
- **The broker never calls `board.py`.** The first cut had the broker "end by calling" the
  dave-owned `board.py` to write the ledger. That had root executing code any `dave` process
  can edit, and it put approvals back into a store every agent process can write, the hole
  decision 10 exists to close. Instead the broker appends each decision, signed (decision 12),
  to its own root-owned stream under `/var/lib/control-room/receipts/board/`, world-readable
  like the broker's receipts (runbook § Control Room). `derive()` reads that stream and trusts
  a decision from nowhere else (§3.6.1).
- The seam (§3.4, §3.6.9) forwards `create`, `brief` and `note` to `board.py`, and decisions to
  the broker, the fork `/api/v1/control/actions` already makes.
- Materially more build than "rule plus detector": allowlist entries, the signed stream, a
  signing key generated at install, hand-install steps. §8 gives it its own increment, I9.

**e. Decision 4, revised 2026-09-28 — Dave decides on the board.** §3.7 is the design. What it
changed elsewhere:
- §3.2: In Review offers Approve, Request changes and Reject. Done is read from `main`, and a
  rejected card closes into Done (decision 13). Blocked counts two requests for changes.
- §3.1, §3.6.1 and §3.6.2: every verb only Dave may take is a broker decision, not a ledger
  event. The `decided` verb and event are gone.
- §3.2a, §3.3, §3.5, §3.6.3, §3.6.4 and §3.6.8: a card run writes a branch at the brief's
  target paths (decision 11), and the brief template gains `## Target paths`.
- §6 drops the Notion row for a card; §3.6.11 is rewritten; §8 changes I1, I3, I4, I5, I6 and
  I9, and adds I10, the watcher's board pass on the vault's own loop.

The draft half of this delta, a branch at the brief's target paths, is superseded by f.

**f. Decisions 11, 12, 15 and 16, taken 2026-10-06.** The research is a Notion page, and the
vault copy is a landed note. Applied the same day:
- §3.7: the draft is the card's page in the Research database; Approve takes the page as it
  stands, and the broker keeps the approved text; the apply lands that text as one note in
  `05_knowledge/research/`, which the watcher checks and merges. The research area and its
  retrieval are new there.
- The brief template loses `## Target paths`, and with it `validate-brief`'s path check, the
  brief contract's `target-paths-under-scope` and the profile's clause; `scope` is a retrieval
  hint only.
- §3.6.3's item 5, §3.6.4, §3.6.5's `must_not` row, §3.6.8's checks, receipt block and sweep,
  §3.6.9-§3.6.12, §3.1, §3.2, §3.2a, §3.3, §3.4, §3.5, §3.8, §4 and §6 follow.
- §8: I3 publishes a page instead of pushing a branch, and shrinks from L to M; I6 gains `land`
  and grows from S to M; I9's approval carries the page text; I10's check becomes one added
  note and its hash, and gains the research area.

### 7.2 Gaps from the 2026-09-26 walk-through

Walking the flow end to end with Dave surfaced four gaps. §3.7 closes two, §3.8 closes a
third, and the fourth is accepted for the pilot.

1. **A Mac session can decide as Dave.** Claude on the Mac reaches the seam over the tailnet
   like Dave's browser does, the seam stamps `actor = dave`, and the broker cannot tell the two
   apart. A step-up check on the decision verbs would prove a human click: a WebAuthn touch in
   the browser, which needs the Control Room on HTTPS (§3.6.11). **Accepted for the pilot,
   2026-10-06:** the worst case is one wrongly approved note in `05_knowledge/research/`, undone
   by a revert. Revisit before dev cards (§5).
2. **`decided` could not reach the broker, and `approvals.tsv` sat inside the research runs'
   write boundary.** **Closed by §3.7:** Done is read from `main`, and the sweep writes no
   decision.
3. **A rejected artifact had no column.** **Closed by §3.7** and decision 13.
4. **No verb edited a card's fields after create,** so Todo could not be reordered, and a
   wrong deadline meant a new card. **Closed by §3.8:** the card popup edits the human-owned
   fields through a new ledger verb, `edit`, and Withdraw closes a card nobody wants.

## 8. Increments

| # | Slice | Size | Depends on |
|---|---|---|---|
| I1 | `bin/board.py`: ledger, events, derivation joined to receipts, to a broker decision stream and to canonical `main`, brief hashing, the `edit` verb and the research date (§3.8), the template, `--help`; `tests/test_board.*` on synthetic cards and a fixture stream | M | — |
| I2 | Brief workflow: `board` run mode and the pick in `agent_propose.sh`, runner (`--allowedTools` includes `WebSearch,WebFetch`, decision 9), verify command, profile, contract, units, override env, manifest entry, tsv row, pinned counts, smoke | M | I1 |
| I3 | Research runner join: the pick in `standing_research.env`; the card run's page in `agent_propose.sh` (`research.md`, the boundary, `research.prev.md` after a request for changes, the publish, decision 11); `bin/notion_research.py` (publish, export, mark) and its tests; the receipt `card` block with the page and its hash; the schema's environment names; profile and contract edits; smoke | M | I1, the Research database |
| I4 | Control Room reads: read model, board page, the card popup read-only, laid out as the §3.8 mockup (`CardDialog` on `DialogFrame` with its new header slot, the `/app/board/<id>` route), with brief provenance, the card's page read through `notion_research.py export` beside the acceptance answers, run ↔ card links, `GET /api/v1/board/decisions`, rebuild | M | I1, I3 |
| I5 | Control Room writes: the board seam for `create` / `brief` / `note` / `edit`, the popup's edit mode: the mockup's inputs, Save on the brief, the note box and the unsaved-edit guard (create is the same popup, empty), state root drop-in. Every decision is I9's | M | I4 |
| I6 | Land and closure: `board.py land` and `sweep` on the sweep timer: each approval landed as one note in `05_knowledge/research/` on a card branch pushed as the App, `agent_inbox_branch_rows.py` skipping `card-` branches, Done by join with canonical `main`, the page's merged path or rejected mark, expiry, the card exceptions into the incident stream | M | I3; fixture decisions until I9 |
| I7 | `queue.md` succession: profile stops reading it, docs and vault note updated | S | I3 |
| I8 | S1: bridge family, vault skill, pointer, README row, manifest `bridge_tools` and `skills`, rendering. In scope from day one (decision 7); buildable alongside I2/I3, not after them | M | I1 |
| I9 | Broker decisions (decisions 10 and 12): the seven Dave-only verbs as allowlisted broker verbs in `/etc/control-room/allowlist.json` and `control_broker.py`, the signed root-owned stream under `/var/lib/control-room/receipts/board/`, the signing key generated at install, the mockup's footer buttons (approve, return, request changes, reject or withdraw, block, unblock) with "Save and approve" and "Save and unblock"; an artifact approval that hands the page text to the broker, which keeps it beside the signed decision | M | I1, I5 |
| I10 | Vault side, on the Mac: the watcher's board pass in `agent_merge_watch.sh` (the signature, one added note, its body hash, `agent_branch.py merge --expect-sha`) with `agent_branch_test.py` cases, the broker's public key pinned, the Notion pass skipping `card-` branches; the research area: `05_knowledge/research/` in `vault_map.md`, and its qmd folder context on the Mac and on the box. Written Mac-side, since the box cannot write `main` | M | I6, I9 |

Each is one brief on the repo's own loop: edit, `bin/deploy`, `bash bin/verify.sh`, PR, Dave
merges, hand-install of the drop-in where one is named. I9 additionally hand-installs its
root-owned files and generates the signing key there, never through `bin/deploy`. I10 runs on
the vault's own loop, on the Mac.

**Before the first brief** (2026-10-06). Every decision in §7 is taken and gap 1 is accepted
for the pilot, so nothing in the design gates a slice any more. Three things remain, none of
them a design question:

- The increments enter the Dev Plan as a phase in `docs/dev-plan-2026-09.md` and as rows in its
  Notion tracker, since the Dev Plan stays the only delivery backlog.
- The Notion Research database exists, is shared with the box's integration, and its id is in
  the box's configuration. I3 needs it; I1 and I2 do not.
- I10 lands after the fix to the watcher's fail-open outcome parsing (§3.7's evidence), made
  separately, since both edit `agent_merge_watch.sh`.

Then I1's brief, on the repo's own loop.
