# Brief: B3 — research runner join (I3)

Spec: `.claude/briefs/agent-board-refinement-2026-09-23.md` §3.6.3 item 5, §3.6.4, §3.6.8, §3.7, §8 I3.
Depends on B1 (#92) and B2 (#94), both merged. D9 (Notion Research database shared with the box
integration, id in box config) is Dave's and unconfirmed: everything here runs against a fake; the
live create-a-page check is the one open item and is reported, not assumed.

## Acceptance
1. `bin/notion_research.py publish|export|mark` — one page per card (key: `Card` property), created by
   the first run and body-replaced by the next; `export` renders blocks back to markdown
   (`--if-exists` prints nothing, exit 0, when the card has no page); `mark` sets state and vault path.
   Database id from `NOTION_RESEARCH_DS` (env, else secrets.env, like the token); absent is a loud refusal.
2. `workflow_receipt.py`: optional `card` block (`id` slug, `workflow`, `brief_hash` 64-hex or absent,
   `page` + `page_hash` together or not at all); old receipts still validate; `SCHEMA_VERSION` unchanged.
   `contract_exec.py --card --card-brief-hash --card-page --card-page-hash`.
3. `propose_receipt.py`: new outcome `CARD` (artifact `notion://<page>`); `--page --page-hash`; any run with
   `AGENT_CARD` passes the `card` block (id, workflow, brief hash from `AGENT_CARD_BRIEF_HASH`).
4. `agent_propose.sh`, proposal mode with a card: no inbox checkout; `research.prev.md` exported before the
   model after a prior page exists; stale `research.md` removed per attempt; after the model the inbox
   mirror must be clean (else `VIOLATION`, discard); then publish `research.md` (fresh) and write
   `published.json`; receipt `CARD`. No fresh file: `NOPROPOSAL`. Card-less runs unchanged.
5. `run_standing_research_cc.sh` cds to `$AGENT_CARD_DIR` when set. `proposal_or_decline.sh` accepts a fresh
   `$AGENT_CARD_DIR/research.md`. `standing_research.env.example` gains the pick line.
6. Profile `standing_research_cc_task.md` gains a CARD RUN branch (tasking from `card.md`, queue not read,
   `research.md` with MET/PARTLY/NOT MET lines). The card-less path and its `queue.md` assertion stay:
   dropping `queue.md` is B7.
7. Contract `standing-research.md`: input row, Outputs row, four checks (`page-names-card`,
   `published-is-this-run`, `acceptance-answered`, `pick-hash-matched`), existing inbox checks n/a with a card.

## Files
bin/notion_research.py, bin/workflow_receipt.py, bin/contract_exec.py, bin/propose_receipt.py,
bin/agent_propose.sh, bin/run_standing_research_cc.sh, bin/proposal_or_decline.sh,
profiles/standing_research*, design/contracts/standing-research.md, tests/*.

## Test plan
tests/test_notion_research.{py,sh} (new, fake Notion), test_propose_receipt.py, test_contract_exec.py,
test_contract_schema.py, test_workflow_receipt*, test_agent_propose_smoke.sh (`card-writes-research-only`,
publish, prev export, violation), test_standing_research_smoke.sh; gate `bash bin/verify.sh` (detached).
