# Open decisions — the sync agenda before Phase B

**Status: ALL NINE CLOSED, 2026-09-01.** This is the single list. It consolidated what D1, D2
and D3 left unanswered, plus the work D1 decided in principle but never implemented (W1-W5).
Every `**ANSWER:**` slot below is filled and committed. Phase B is unblocked.

**Read the answers, not the questions.** Six of the nine questions rested on a premise that did
not survive measurement — D3's ("no skill index", "four skills"), D6's ("resolve each workflow to
a suite"), D7's ("how do we evaluate S3"), D5's ("~8 runs each"), D8's ("compare source to the
deployed copy") and D9's ("scope to outward rules"). In each case the question is preserved
unedited and the answer states the correction. A brief written from a question alone will
implement the wrong thing.

**How it was closed:** answered inline under each item, the same way D1 §7 was closed. That
worked — the answers stayed attached to the evidence instead of living in a chat scrollback.
Where a later measurement contradicted an earlier answer, the earlier answer was **rewritten in
place** (D8's cleared baseline, corrected while measuring D5), never appended to: a decision doc
carrying two contradicting measurements of the same thing is worse than one carrying neither.

---

## Where each session landed

| | Doc | Decisions | State |
|---|---|---|---|
| D1 | `workflow-registry.md` | 8 | **all closed** 2026-09-01 (`ed568f8`) |
| D2 | `agent-model.md` §8 | 5 open + 1 withdrawn | **all closed** 2026-09-01 |
| D3 | `eval-spec.md` §8 | 4 | **all closed** 2026-09-01 |

D1 also left **four work items decided in principle and not done** (W1–W4 below). They are
not questions; they are the backlog D1 handed forward.

---

## The nine open decisions

### D1 — Deny the outward connectors in `~/.claude/settings.json`
*(D2 §8.1)*

Gmail `send_message`, M365 `outlook_send_mail`, Drive `share_file` and Figma are live in
every Buzz agent session, on a box whose charter is "no email, no social, no messaging
humans from this box — it holds no outward credentials, ever." The charter is true about
*credentials* and false about *tools*: `claude-agent-acp` sets
`settingSources: ["user","project","local"]` and agents run with cwd `/home/dave`, so
`~/.claude/settings.json` governs all five. Its deny-list covers the four secret paths and
Notion, and nothing else.

- **Cost:** one deny line each. Nothing the fleet uses today.
- **Catch:** one settings file governs *your own interactive sessions here too*. A split
  policy needs a wrapper injecting `--settings`.
- **Recommend:** yes. The mechanism is proven — the Notion deny dropped tools mid-session.

**ANSWER (2026-09-01): DENY ALL FOUR, AND SPLIT THE POLICY — agents strict, Dave open.**

Measured across **479 transcripts, the box's entire history**, before deciding:

| connector | tool schemas | invocations, ever |
|---|---|---|
| Figma | 33 | **0** |
| Microsoft 365 | 41 | 8 — *all reads* |
| Gmail | 29 | **0** |
| Google Drive | 11 | **0** |

The 8 M365 calls were `sharepoint_search` x3 + `read_resource` x4 (2026-08-03) and one
`outlook_calendar_search` (2026-08-09). **No outward action has ever been invoked from this
box** — no `send_message`, no `outlook_send_mail`, no `share_file`, not once. Method note: the
first run of this measurement globbed `*/*.jsonl`, matched **zero files**, and returned a clean
`0` for every connector. A count over a path that does not exist is not evidence of absence —
assert the corpus is non-empty first, and keep a positive control (`mcp__qmd__*`, 85 calls) in
the same query.

**`permissions.deny` removes the tool definition from the prompt, not just the call.** Proven
in the same corpus: Notion, denied 2026-08-03, contributes **0** definitions to today's
transcripts, while undenied Figma contributes 198-495 each. So this pays twice — it closes the
charter gap *and* drops **114 tool schemas** from every request on a fleet where marcus is
actively failing `Prompt is too long` x258 as the 20-channel DAG root.

**Capability loss is zero, because no capability this box depends on lives in the
`mcp__claude_ai_*` namespace.** Notion is the worked control: denied 08-03, and the
`buzz-notion-broker` was built for augustus on **08-10, seven days later, and works**. The two
real paths are untouched — 7 `notion_*` tools via `buzz-team-mcp.py` -> `buzz-notion-broker.py`
(`--user` unit, active since 08-17) for Buzz agents, and five REST helpers (`notion_rest.py`,
`notion_daily.py`, `notion_research_page.py`, `notion_markdown.py`, `notion_content_migrate.py`)
for scheduled jobs. The deny is what *enforces* the standing Notion-REST-only directive.
Figma has never been called here and Figma work is Mac-side. M365/Gmail/Drive were tools without
credentials — and could never serve a scheduled job anyway (zero MCP, 9/9 runners verified), so
a real calendar fix has to be a scoped REST helper regardless.

**General rule this establishes:** a capability this box depends on lives in a script or a
broker it owns, never in an account-level OAuth connector. Connectors cannot reach the scheduled
surface, cannot carry policy, and cannot be scoped per-agent.

**Split policy — the obvious implementation is a silent no-op; use `CLAUDE_CODE_EXECUTABLE`.**
Read from the installed `claude-agent-acp` 0.64.0:

- `dist/acp-agent.js:4156` sets `settingSources: ["user","project","local"]` on the real session
  query, so `~/.claude/settings.json` **does** govern agent sessions. (`dist/index.js:47`'s
  `settingSources: []` is unrelated — it reads the managed-policy tier only, to hoist env vars.)
- **`--settings` in `BUZZ_ACP_AGENT_ARGS` would have been accepted and ignored.** `index.js`
  parses only `--version`/`-v` from argv; caller options arrive over ACP `_meta` as
  `userProvidedOptions`. The flag would have looked configured and done nothing — the same
  class as every "config edit is inert until the process reloads it" trap in `~/CLAUDE.md`.
- The working seam is **`CLAUDE_CODE_EXECUTABLE`** (read 3x in `acp-agent.js`, alongside
  `pathToClaudeCodeExecutable`): point it at a wrapper that execs the real `claude` with
  `--settings <strict file>` appended. `claude --help` confirms `--settings <file-or-json>` and
  that it is an *additional* source ("managed settings and --settings still apply"), so deny
  lists union — a `--settings` file can only tighten, never loosen.
- Rejected `CLAUDE_CONFIG_DIR` (the other candidate seam): it relocates credentials, projects
  and the shared file-memory pool at `~/.claude/projects/-home-dave/memory/` that all four
  agents and Dave's own sessions deliberately share. Too wide.

Resulting shape:

- `~/.claude/settings.json` — unchanged. Keeps the 10 secret-path denies and
  `mcp__claude_ai_Notion` (the REST-only directive binds Dave too). Dave's interactive box
  sessions keep Gmail/M365/Drive/Figma.
- `~/.config/buzz-team/agent-settings.json` — new strict file, a **superset**: every deny above
  plus `mcp__claude_ai_Gmail`, `mcp__claude_ai_Microsoft_365`, `mcp__claude_ai_Google_Drive`,
  `mcp__claude_ai_Figma`. Written as a superset so it is correct whether `--settings` merges or
  replaces.
- `~/.config/buzz-team/claude-agent-wrapper.sh` — `exec claude --settings <strict> "$@"`.
- `buzz-agent@.service` — `Environment="CLAUDE_CODE_EXECUTABLE=%h/.config/buzz-team/claude-agent-wrapper.sh"`.

**Accepted cost, and its mitigation:** this creates a second policy file that can drift from the
first — the exact class D8 exists to catch, now sitting in the security layer. Mitigate inside
the D4(b)/D8 suite with one assertion: `agent-settings.deny` must be a **superset** of
`settings.deny`. A deny added to the base file and not the strict file is then a red gate, not a
silent hole. Verify the split the way `check-loaded.sh` verifies a `.env` — by what the running
process loaded, not by what the file says.

---

### D2 — Fix the alert throttle now, or fold it into a Phase-B brief?
*(D2 §8.3, covering §6.2 and §6.3)*

§6.2: the failure-alert throttle has been deployed-but-unwired for 18 days. `bin/deploy`
copied the script; nobody wrote `/etc`. 19 of the last 60 alert lines are the same
`qmd-refresh` message. §6.3: three repo unit files are *behind* `/etc`, and four live units
have no repo source at all.

- **Recommend:** fix §6.2 now — it is degrading alerting today. Fold §6.3 into Phase B.
- §6.6 (per-workflow locks) and §6.7 (import the four orphan units) are Phase B either way.

**ANSWER (2026-09-01): FIX BOTH NOW — the throttle is wired, and alert coverage is closed.**

Done and verified on the box, not merely committed.

**The throttle (§6.2) is live.** `/etc/systemd/system/agent-alert@.service` now execs
`bin/agent_alert.sh %i` instead of the inline `/bin/sh -c`. Proven end-to-end with a
throwaway failing unit through the real chain: two failures produced two records in
`~/logs/agent-alert.log` — the second reading
`[notification throttled: failure 1 since the last alert]` — and exactly **one** outbound
delivery, receipt `2026-09-01T14:12:04Z`, `discord_result: ok`, `buzz_result: ok`,
`outcome: delivered`. Two records, one notification, which is the design.

**Two corrections to the framing this decision was written on.**

1. *The alert volume was not chronic noise.* 27 alerts across 11 units in seven days
   looked like a standing duplication problem. It was **one incident**: headless Claude
   Code's OAuth session expired ~08-27 and every scheduled job failed identically with
   `Failed to authenticate: OAuth session expired and could not be refreshed` until Dave
   re-authorised on 08-31 ~11:40. Alerts stop dead at 11:42 and there have been none
   since. The daily counts (08-28:8, 08-29:5, 08-30:5, 08-31:6) read as ongoing only
   because nobody noticed 08-31's stopped mid-morning — presence is not freshness.
   The throttle would still have helped, collapsing ~27 alerts into ~11 first-failures;
   it just was not fixing what the doc said it was fixing.

2. *`fleet-eval` is deliberately unrouted and stays that way.* `systemctl --failed`
   named it, and the obvious reading — an eval harness that fails silently — is wrong.
   Its own header says `NO OnFailure=`, deliberately: it exits 1 on a regression and
   `--deliver` already posts the scorecard to `#ops`, so wiring the alert path would
   give one problem two notifications on different surfaces. Verified rather than
   assumed: this morning's `probe/p2_publish_approve` regression **was** delivered at
   `05:09:04Z`, discord ok, buzz ok, outcome delivered. Its non-zero exit is the intended
   quiet second signal and clears on the next green run. The receipt gap 08-16 → 09-01 is
   fourteen clean days, not fourteen lost alerts.

**Alert coverage (the genuine half).** Four units had no route and no one delivering on
their behalf: `local-tier-eval`, `memory-consolidation`, `scorecard` (whose
`ExecStartPost=deliver_scorecard.sh` only runs when `ExecStart` succeeded, so a failing
run delivered nothing at all), and `ttm-pool-drain` — which was untracked in `/etc`
entirely and is now adopted into `systemd/`. All four carry `OnFailure=agent-alert@%n.service`
in repo and `/etc`, in sync, confirmed live via `systemctl show`.

**Sequencing constraint, now recorded in `systemd/ttm-pool-drain.service`'s header.**
That unit fires **every two minutes**. Wiring its `OnFailure=` before the throttle existed
would have emitted ~720 notifications a day into Discord and Buzz. So the throttle is not
an independent improvement to alerting — it is a **precondition for widening alert
coverage at all**, and the two halves of this decision had to be done in that order.

**§6.3 re-measured, and it was right.** Three repo unit sources still differ from `/etc`
(`bd-stall-radar`, `m1-signal-scan`, `weekly-pre-assembly`) and — filtering Ubuntu stock —
three box units still have no repo source (`fleet-turn-check`,
`praetorium-content-strategy-research`, `praetorium-faceless-content-research`, plus their
timers). The doc said four orphans; `ttm-pool-drain` was the fourth and is now adopted.
**Both remain Phase B**, as recommended — but note `fleet-turn-check` is among the orphans,
and it is the gate that proves an agent can complete a turn.

**Two defects this surfaced, not fixed here, for the Phase-B list.**
- *The runner's stderr is captured but unfindable.* `agent_propose.sh:309` writes every
  attempt to `logs/agent_run.log` — untimestamped and interleaved with report prose from
  every job. The journal shows only `FAIL: runtime failed after 2 attempts`; finding the
  four-word cause of a four-day outage meant grepping 547 KB. Per-job, timestamped runner
  logs would have made this a ten-second question.
- *`Persistent=true` does not re-fire a slot that fired and failed.* Four nights of
  research runs were recovered only because someone hand-wrote four make-up `OnCalendar`
  lines. An unattended job that fails during an absence is not recovered by its own
  schedule, and nothing distinguishes "did not run" from "ran and produced nothing".

Commit: `28eda21` (unit sources) + this file.

---

### D3 — Skills posture
*(D2 §8.4)*

S1 and S2 have no skill index at all; the vault's 32 `08_skills/*/SKILL.md` are reachable
only by path, i.e. only if an agent remembers they exist. S3/Hermes has the only real index
(148 files), and `disabled` removes zero allowlisted skills on all four profiles.

Options, not exclusive: (a) leave it — agents read the vault and it works; (b) register the
role-relevant vault skills as Claude Code skills so they are *offered* rather than
remembered; (c) retire the S3 allowlist investment now that hermes is a one-off queue.

- **Recommend:** (b) for the four skills the content and research workflows actually name.
  Leave (c) until a card actually fails.

**ANSWER (2026-09-01): (b) YES — as POINTER skills, never copies — AND fix augustus's extraction.
The premise above is wrong twice, and the fix augustus needs is not a skill.**

**Correction 1 — S1 and S2 already have a skill index.** `~/.claude/skills/` does not exist,
which is true and misleading. Measured by probe: a `SKILL.md` dropped there is listed by name
in a run shaped exactly like S2 (`claude -p --permission-mode bypassPermissions
--strict-mcp-config --mcp-config '{"mcpServers":{}}' --allowedTools "Bash,Read,Write,Glob,Grep"`),
and that run already saw **25 skills** — the 7 `shared@jbuitenhuis` ones this doc counted, the 4
in `~/.claude/commands/` (`finish`, `implement`, `plan-feature`, `ship`), and ~14 Claude Code
built-ins (`code-review`, `security-review`, `simplify`, `loop`, `schedule`, `workflow-authoring`,
`dataviz`, …). So (b) is not "build an index". It is "add files to one that already exists,
already loads on both surfaces, and needs no runner change."

**Correction 2 — one skill is named by a live workflow, not four.** Grep across all
`profiles/*.md`: **5 references, 1 distinct skill** — `08_skills/linkedin-content-engine`, by
`augustus_content_task.md` (3) and `augustus_polish_task.md` (2). No research profile names any
vault skill. "The four skills the content and research workflows actually name" was never
measured.

**Third finding, from the same probe: `--allowedTools` is inert under `bypassPermissions`.**
`Edit` was absent from the allowlist and was nonetheless available and used to edit a file
successfully. §2's surface table lists S2's tool set as "explicit `--allowedTools`"; that is not
a containment mechanism. S2's real containment is `--strict-mcp-config --mcp-config '{}'` (no MCP
server is loaded, so no connector tool exists) plus `agent_propose.sh`'s write boundary. **§6.1
credits the wrong mechanism** for the outward-connector guarantee — the conclusion holds, the
reason does not. Anyone who drops `--strict-mcp-config` believing the allowlist is the guard
removes containment with no error. Correct §2 and §6.1; this does not disturb D1, whose chosen
mechanism is `permissions.deny`, which *is* enforced under bypass (this session cannot read its
own deny-listed paths).

**The asymmetry that decides scope: (b) cannot reach the only agent that uses a skill.**
`buzz-agent@augustus.service.d/harness.conf` sets
`BUZZ_ACP_AGENT_COMMAND=/usr/local/bin/codex-acp` with its own `CODEX_HOME`, and Codex has no
skills mechanism at all (`codex --help` offers no skill flag). `augustus-content` is
`surface = "buzz_dispatch"` → S1 → codex. So registering `linkedin-content-engine` offers it to
marcus, claudius, trajan, aurelian and every S2 job — everyone except augustus.

**And his workaround has already drifted silently.** `augustus_content_task.md:69-79` states the
problem outright ("There is no skill *tool* on this harness — a skill here is markdown you read")
and extracts the 37,631-byte `SKILL.md` by pinned line numbers:
`sed -n '19,36p;53,78p;100,134p;168,235p;341,353p;414,423p'`. Measured against the file today
(453 lines, last edited 2026-08-14): four ranges land exactly, **two are off by 2 lines**.

| pinned range | intended section | actual | consequence |
|---|---|---|---|
| `341,353p` | Step 6 — first-comment strategy | 343-355 | opens on Step 5's Codex sandbox note; drops the last 2 lines, incl. "Bridge to the adjacent audience without hijacking the post." |
| `414,423p` | Variations mode | 416-425 | drops "Recommended N: 3 (more than 5 is decision fatigue)" |

Nothing errors, no suite covers it, and **the pins live in this repo while the file lives in the
vault** — two repos with no shared gate, so no commit here can ever see the target move. The
drift is 2 lines today and only grows. This is the live defect; a skill registration would not
have touched it.

**CORRECTED 2026-09-02, re-measuring the same unchanged file (453 lines, mtime 2026-08-14
18:44). The measurement above is right about the two ranges it names and wrong about the
count: three of six are off, not two.** The reading above is kept rather than rewritten,
because the way an incomplete measurement gets caught next time is by leaving both readings
visible with their dates.

| pinned range | intended section(s) | actual extent | consequence |
|---|---|---|---|
| `168,235p` | Step 2.7 + Step 3 + Step 4 | 168-236 | **drops line 236 — self-check item 11, the AI-tell scan** |

**The third miss is the most consequential of the three, and it is the one an off-by-two
framing hides.** The other two lose a line of guidance at a section edge. This one makes the
profile lie about itself: `augustus_content_task.md` tells augustus that `ai_tells.md` carries
"11 structural AI tells + the de-slop pass + **self-check #11**", while the extraction had been
handing him a Step 4 that stops at item 10. The profile promised a check the skill read
silently withheld — for the whole time the pins were live.

**`augustus_polish_task.md` has nothing to fix.** Part 1's decision below says to fix it too;
measured 2026-09-02 it carries no pinned ranges at all — it reads `references/voice.md` and
`references/ai_tells.md` in full, by exact path (`profiles/augustus_polish_task.md:26-28`).
Converting a whole-file read into a section extraction for symmetry would add the failure mode
this decision exists to remove, so it was deliberately left alone.

**BUILT 2026-09-02 (brief 4), part 1 only.** `bin/skill_sections.sh` resolves by heading text —
whole-string equality, never a prefix; extent to the next heading of the same or higher level so
a section carries its subsections; all-or-nothing output so an unresolved name cannot leave a
partial read on stdout. It lives in `bin/` and not inside the profile because `bin/verify.sh`
lints and syntax-checks `bin/` and **nothing in this repo ever parses, lints or executes a shell
line embedded in profile markdown** — that asymmetry is why the pins rotted unobserved.
`tests/test_content_skill_extract.sh` is the shared gate, and it executes the profile's own
command rather than pattern-matching it. Part 2 (pointer skills) is untouched and still open.

**Decision, in two parts.**

1. **Fix the extraction (the real fix).** Replace the six pinned ranges in
   `augustus_content_task.md` (and `augustus_polish_task.md`) with heading-anchored extraction
   that **fails loudly** when a named section is absent, rather than silently returning the
   wrong lines. A missing heading must abort the run, not degrade it. Needs a suite —
   `tests/test_content_skill_extract.sh` — asserting every named section resolves against the
   live vault file. That test is the shared gate the two repos do not otherwise have.

2. **Register pointer skills under `~/.claude/skills/`.** **A pointer, never a copy:** each
   `SKILL.md` is a few lines naming the canonical vault path and telling the agent to read it.
   A copy would go stale against the vault in exactly the way the line pins just did, and would
   create the second source of truth the vault's one-fact-one-place rule exists to prevent.

   Starting list, grounded in the vault's own `08_skills/skill_index.md` categories against each
   persona's charter role — **to be confirmed in the Phase-B brief, not treated as settled here**:

   | persona | pointer skills | grounding |
   |---|---|---|
   | augustus | linkedin-content-engine, linkedin-review, blog-engine | index "Content & LinkedIn"; **reaches him not at all — he is on codex.** Registered for whoever else drafts. |
   | claudius | prospect-research, meeting-prep, investment-research | index "VP Sales Skills" + "Investing" |
   | trajan | systematic-debugging, test-driven-development, verification-before-completion, spec-to-code-enforcement | index "Development Skills" |
   | marcus | weekly-review, agent-inbox-sync, post-call-capture | index "Daily Operations" |
   | aurelian | none | read-only by calibration pin |

   **Honest caveat: 1 of these 14 is named by a live workflow.** The other 13 are offered on role
   grounding, not demonstrated demand. That is the point of "offered rather than remembered" —
   but it should be recorded as a bet, and revisited by measuring which pointers are ever invoked.

   **`morning-startup` and `eod-wrap` are deliberately excluded.** `CLAUDE.md` records the daily
   rhythm jobs as a *port* of those two Mac skills, with the Mac copies canonical for interactive
   runs. Registering them would offer an S2 daily-plan job a competing procedure to the task
   profile it already has. **General rule: a pointer skill must not duplicate a task profile that
   already owns the same surface.**

- **Option (c) is not decided here** — see D7, where the measurement that settles it lives.
- **Dependencies:** part 1 gives `augustus-content` a second suite (R15b). Part 2 is independent.

---

### D4 — Is the manifest the source of truth?
*(D2 §8.5)*

i.e. may Phase B generate each wrapper's `--allowedTools` from `design/agents/*.toml`
rather than the reverse. This is the load-bearing one: it decides whether the manifests are
documentation or configuration. Everything in D3's coverage checker assumes the former is
false.

- **Recommend:** yes.

**ANSWER (2026-09-01): BINDING, CHECKED — option (b) of three.**

Not a yes/no. Measured before deciding: nine `run_*_cc.sh` runners carry `--allowedTools`,
collapsing to **four** distinct literals, a clean 2x2 of {may edit vault} x {may reach web}:

| set | tools | runners |
|---|---|---|
| vault-writer | `Bash,Read,Write,Edit,Glob,Grep` | bd_followup_drafts, knowledge_digest, raw_ingest |
| vault-writer+web | + `WebSearch,WebFetch` | m1_signal_scan, standing_research |
| reporter | `Bash,Read,Write,Glob,Grep` | daily_rhythm, overnight_morning_report, weekly_pre_assembly |
| reporter+web | + `WebSearch,WebFetch` | standing_research_topic |

The three postures were (a) documentation, (b) binding and checked by a test, (c) binding and
generated by codegen. **(b) chosen.** Runners keep their literal `--allowedTools`; a suite
under `tests/` asserts runner == manifest and fails `bin/verify.sh` on drift.

Rejected (c) — codegen — for a specific reason: `bin/deploy` performs **zero** codegen today
(measured, grep count 0); it is a pure copy. This box's demonstrated failure mode all week has
been *source and deployed disagreeing* (D2 §6.2 an 18-day unwired throttle, §6.3 repo units
behind `/etc`, §6.7 four live units with no repo source). Generation would have to emit into
both trees or it adds a **third** copy of the truth to a system already losing track of two,
and a generated runner cannot be hand-patched during an incident.

Rejected (a) — documentation — because it rots exactly the way this registry's own next-elapse
values did: wrong by *day* for three workflows, unnoticed until D2 read `systemctl cat`. And
D6's coverage checker would then be grading a fiction.

**Consequence — this merges D4 and D8 into one mechanism.** The check reads a runner file and
compares it against the manifest. Run the same check against the **deployed** tree
(`~/agent-workforce/bin/`) and it is D8's source-vs-deployed drift assertion, unchanged. One
suite, two invocations. Build it once.

**Tool profiles: NO — per-workflow literals, not four named profiles.** Every workflow spells
out its own list; no indirection to follow, and a one-off exception needs no new profile name.

Two schema consequences that follow, and are not optional:

1. **`tools` must move from `[surfaces.*]` to `[[workflows]]`.** It sits at surface level in all
   five manifests today, which is already lossy — the scheduled surface holds four distinct sets,
   and `claudius.toml:25` carries a `tools_web = [...]  # standing-research + m1 only` side-key
   precisely because one surface-level list could not express two workflows. That hack dissolves.
2. **A workflow with no model runtime must declare that explicitly**, e.g. `tools = "none"` with
   `runner_kind = "shell"`. Trajan's 12 workflows are plain shell/systemd jobs and correctly carry
   no `--allowedTools`. If absence is implicit, a runner that *loses* its tools line reads
   identically to one that never had one — the same silent-absence class as the empty `Synced At`
   column and the `Result=success` reset default. The check must be able to fail on a missing
   declaration, which means the declaration has to exist.

---

### D5 — Do you want a *standing* content-research workflow?
*(D2 §8.6 — replaces the withdrawn timer-fix decision)*

The two campaigns end 09-03 and 09-04 having delivered ~8 runs each on two named topics.
A permanent version is a different thing: it needs topic rotation, a slot that is not 01:30
(the `augustus-content` lock collision of §6.6), and its own registry row.

- **Recommend:** no for now. Let them expire; revisit when the content pipeline's existing
  backlog is consumed.

**ANSWER (2026-09-01): NO — confirmed, but the stated reason is wrong and "let them expire" is
not a no-op. The campaigns have delivered HALF what this question credits them with, and they
leave three things behind that need an owner.**

**The "~8 runs each" premise is wrong by 2x.** Read from the producer's own counter —
`~/agent-workforce/var/notion_research_pages.json`, which `bin/notion_research_page.py` maintains
— not inferred from timer slots:

| slug | `run_count` | design target (`--total-runs`) |
|---|---|---|
| `content-strategy-2026` | **4** | 6 |
| `faceless-content-product` | **4** | 6 |

Eight runs **across both campaigns**, not each. The original claim counted scheduled slots. This
is the readiness-report class landing inside our own design doc: a count that was never asked of
the thing that produces it.

**Because 8 of 16 scheduled runs failed — four consecutive nights per campaign — and the
alerting worked perfectly the whole time.** From `cost.log` and the journals:

| campaign | delivered | failed | failure signature |
|---|---|---|---|
| content-strategy (23:00) | 08-25*, 08-26, 08-31*, 08-31 | 08-27, 08-28, 08-29, 08-30 | `outcome=FAIL run_seconds=33 attempts=2` |
| faceless-content (01:30) | 08-26, 08-27, 08-31*, 09-01 | 08-28, 08-29, 08-30, 08-31 | same |

*(\* = hand-run, not a scheduled firing. Only **5 of the 8 deliveries were scheduled**.)*

Cause, per the make-up timer's own header comment: `"Failed to authenticate: OAuth session
expired and could not be refreshed"` — the 2026-08-27 OAuth outage. **`OnFailure=agent-alert@%n`
fired every time**: 9 alerts, all present in `~/logs/agent-alert.log`, correctly timestamped. And
both campaigns still sat dead for four consecutive nights until Dave reauthorised by hand on
08-31. **Alerting is not recovery** — and `Persistent=true` does not re-fire a slot that fired and
failed, so every lost night is lost permanently unless a human reschedules it, which is exactly
what the two `/etc` make-up timers are.

**That is the real argument against a standing version, and it is stronger than "revisit later".**
A permanent workflow inherits a failure mode that is silent to everything except a log nobody
reads, unrecoverable without hand-rescheduling, and capable of eating four nights before anyone
notices. Topic rotation and a non-01:30 slot are the *easy* half. Fix the recovery story first —
that is D9 territory (a must-run rule with teeth) and the `fleet-turn-check` pattern, not a new
timer.

**Two premises in the question that measurement does not support:**

- **The §6.6 01:30 lock collision has never occurred, and could not have.**
  `augustus-content.timer` is `enabled` but was **not active** — `systemctl show … -p
  LastTriggerUSec` plus `journalctl -u augustus-content.timer` put its `Started` at
  **2026-09-01 08:15:39**, with no reboot behind it (`uptime -s` = 2026-08-17). It fired **once
  in eight days**, as a `Persistent` catch-up at 08:15, while the campaign ran at 01:30:04 on
  every one of those nights. So the overlap is structural (`*-*-* 01:30` + `RandomizedDelaySec=5min`
  against a job that starts at 01:30 and runs 4.5-7 min) but **untested**. §6.6 states a
  prediction as an observation; mark it unverified. `enabled` is not `active`, and `list-timers`
  does not show a stopped timer at all.
- **"Revisit when the content backlog is consumed" rests on a consumer that is barely running.**
  The nightly pitch+draft job that draws the backlog down is `augustus-content` — the same job
  that ran once in eight days. The backlog is not being consumed at the rate the condition
  assumes, so the trigger for revisiting would never fire on its own terms.

**Decision: no standing workflow. Let both campaigns finish their remaining nights.** Three
things must be owned when they do — none of which "let them expire" covers:

1. **Delete the two `/etc` units after the last firing** (content-strategy 09-03 23:00, faceless
   09-04 01:30). Left in place they are expired `OnCalendar` lists that will never fire again —
   permanently green in `list-timers`, permanently incapable of producing anything. That is the
   exact shape of the mirror case D8 records.
2. **Reconcile the overshoot.** 4 runs + 3 remaining nights each = **7 against a target of 6**.
   The make-up schedule recovered the 4 lost *scheduled* nights but never deducted the 08-31
   hand-run. Harmless; recorded so the run counts are not later read as a defect.
3. **The output has no home in this repo.** Neither campaign's artifact is a proposal
   (`proposal=none` on all 16 rows, `AGENT_RUN_MODE=ops`, no `ExecStartPost` delivery by design)
   — it is a Notion page plus `run_count`. When the units go, `var/notion_research_pages.json`
   and the two Notion pages are the only surviving record. Note that in the registry so a later
   cleanup does not read them as orphans.

**Revisit condition, replacing the vague one:** propose a standing content-research workflow when
(a) `augustus-content` has run on its own schedule for 14 consecutive days, and (b) an auth
failure is recoverable without a hand-written make-up timer. Both are measurable; "backlog
consumed" was not.

---

### D6 — Build the workflow-coverage checker as the first Phase-B item?
*(D3 §8.1)*

9 of 26 workflows have a suite that owns them. Nothing on the box can report that, because
no layer knows the workflow list — the manifests are the first artifact that does. The
checker reads `design/agents/*.toml`, resolves each live workflow to a suite, and fails on
an unowned one.

- **Depends on:** W5 (explicit per-workflow `status`), and on D4 being yes.
- **Recommend:** yes. It is small, and it grades every brief that comes after it.

**ANSWER (2026-09-01): YES — but with a DECLARED join, not an inferred one. The premise above is wrong.**

The sentence "resolves each live workflow to a suite" has no implementation that works. Four
join rules were measured against the live tree; all four disagree, in both directions:

| join rule | covered | failure |
|---|---|---|
| unit name appears in suite text | 17 | **false green** — `agent-workforce-auto-sync` "covered" by a `list-timers` *fixture string* in `test_local_tier_eval_score.sh` |
| suite filename ~= unit name | 7 | false red on `augustus-content`, `agent-proposal`, `qmd-refresh`, `memory-consolidation` |
| manifest `runner` field | 7 | false red on **both** rhythm jobs: manifest records `run_daily_rhythm_cc.sh`, the suites name the wrappers |
| `runner` + resolve wrapper chain | 9 | right answer, wrong mechanism — credits daily-plan with `eod_summary_smoke` and vice versa, because they *share* an implementation |

Two structural reasons no rule can be made to work:

1. **13 of 26 entries carry no `runner`** (every trajan platform job), so that key is
   unavailable for half the registry.
2. **Coverage can sit three hops out.** `agent-inbox-sync` -> `bin/agent_inbox_pipeline.sh` ->
   `bin/agent_inbox_notion_sync.py` -> `test_agent_inbox_body_sync.sh`. Following one wrapper
   level is not enough, and following N levels is what produces the shared-implementation
   false green above.

**Decision: add `suite = [...]` to every manifest entry, hand-declared, and have the checker
read it.** Same shape as W5's `status` — it converts an inference problem into a data problem,
which is why the count stops moving. The checker asserts, per entry:

- `status == "standing"` and no `suite_exempt` => `len(suite) >= 1`
- every path named in `suite` exists on disk
- every `bin/` entrypoint is **reachable** — exec'd by a live unit, or invoked by a script that
  is. A suite whose only subject is an unreachable script is an orphan.

The obvious reverse rule — "every `tests/test_*.sh` is claimed by >= 1 entry" — was measured
and **rejected**: 23 of 41 suites are unclaimed and most legitimately test *libraries*
(`notion_rest`, `notion_markdown`, `buzz_deliver`, `proposal_or_decline`, `qmd_status`), not
workflows. It would fire 23 false positives to catch one real orphan. The unit-name variant is
no better — it catches only `not-yet-ported.service`, a fixture placeholder inside
`test_audit_buzz_dual_run.sh`. **Reachability is the rule that works**, and it pinpoints the one
real case with no false positives.

**Out-of-repo workflows are exempt but never invisible.** Three standing workflows exec
scripts that are not in this repo — `fleet-turn-check` (`~/.config/buzz-team/`),
`ttm-pool-drain` (`/usr/local/bin/`, root-owned) and `buzz-pr-watch` (`~/.local/bin/`, a
`--user` unit). They carry `suite_exempt = "<reason>"` and are exempt from needing a suite, but
the checker **prints them as a named list on every run**. The exemption gets its own field, `suite_exempt = "<reason>"`, **not** `in_repo`: D2 set
`in_repo = true` on ttm-pool-drain meaning *the unit file* was adopted into `systemd/`, while
its *script* is `/usr/local/bin/ttm-pool-drain` and is not here. One word, two referents — a
checker keying on `in_repo` would exempt the wrong set. Exempt, not hidden — `fleet-turn-check` is the gate that proves an agent can complete
a turn, and it is exactly the kind of thing that disappears from a whitelist.

**The recorded figure was wrong three ways.** "9 of 26" in the headline, 11 implied by this
doc's own table (which lists 15 uncovered), and **16 covered / 10 uncovered** on measurement.
Corrected in `design/eval-spec.md` §8.1 in the same commit. The measured mapping, which the
`suite` fields are seeded from so Phase B does not re-derive it:

| workflow | suite(s) | found via |
|---|---|---|
| augustus-content | `run_content_via_buzz` | runner |
| content-change-dispatch | `content_change_dispatch`, `content_dispatch_state_hold` | name |
| knowledge-digest | `knowledge_digest_smoke` | name + runner |
| agent-proposal | `standing_research_smoke` | runner only |
| raw-ingest | `raw_ingest_smoke` | name + runner |
| bd-followup-drafts | `bd_followup_drafts_smoke` | name (owns a **dormant** unit) |
| praetorium-daily-plan | `daily_plan_smoke` | wrapper, not the recorded runner |
| praetorium-eod-summary | `eod_summary_smoke` | wrapper, not the recorded runner |
| weekly-pre-assembly | `weekly_pre_assembly_smoke` | name |
| fleet-eval | `fleet_eval` | name |
| local-tier-eval | `local_tier_eval_score` | name |
| scorecard | `scorecard` | name |
| memory-consolidation | `consolidate_memory` | ExecStart script |
| qmd-refresh | `vault_sync_guard` | ExecStart script |
| agent-inbox-sync | `agent_inbox_body_sync`, `agent_inbox_branch_rows` | **hop 3** |
| inbox-backlog-alert | `buzz_adapters` | ExecStart script |

Uncovered — 10, of which 2 campaign + 1 dormant (`bd-stall-radar`) + 7 standing. Of the 7
standing, 3 are `suite_exempt` (above) and **4 are writable today**: `m1-signal-scan`,
`overnight-morning-report`, `agent-workforce-auto-sync`, `overnight-pre-snapshot`. The
checker therefore ships **red with 4 named failures**, deliberately — those four are the
Phase-B backlog it exists to produce. `overnight-morning-report` is the sharp one: it is
uncovered and it is the unit carrying the entire recurring reporting-defect class.

One live orphan, and it is the reachability rule's test case:
`tests/test_content_inbox_finalize.sh` tests `bin/content_inbox_finalize.py`, whose unit was
**removed 2026-09-01** (`systemd/archive/content-inbox-finalize.{service,timer}`, nothing in
`/etc`). The script is still present and still gated by `verify.sh`, so nothing goes red. It is
exec'd by no unit, and its only other mention in `bin/` is a comment at `notion_rest.py:241`
naming it *"the retired"* path — i.e. the codebase already knows, in prose, what no check
asserts. Same shape as every defect in the reporting class: the fact was written down and
nothing was measuring it.

- **Depends on:** W5 (done, `3a52d42`), D4 (yes, `b49606b`).
- **Sequencing:** the `suite` + `suite_exempt` fields land now as a W-item (manifest data, same
  class as W5). The checker script itself is the first Phase-B brief.

---

### D7 — Leave the Hermes kanban surface unevaluated?
*(D3 §8.2)*

Nothing grades a kanban card's execution. This may be correct — but it should be a decision
rather than an omission.

- **Recommend:** yes, leave it; fold into D3 (skills posture) rather than answering twice.

**ANSWER (2026-09-01): INVESTIGATE RETIRING S3 ENTIRELY — investigation done, and it concludes
RETIRE. The question "how do we evaluate the kanban surface" was premature: nothing runs on it.**

**S3 is not lightly-used, it is idle.** Measured across the board, the gateway and the runners:

| measurement | value |
|---|---|
| cards on the board | 11 |
| last card dispatched to completion | **2026-07-20** (43 days ago) |
| SEO cards assigned `trajan`, status `blocked` | 5, since **2026-07-10** (53 days) |
| `hermes cron list` | **"No scheduled jobs"** |
| listening socket for the dashboard | **none** — nothing bound |
| cards carrying a non-empty `skills:` field | **0 of 11** |

That last row settles the parent question directly. The NUC-42 per-agent allowlists (marcus 46,
trajan 44, claudius 25, augustus 23) are selected from by the **card's** `skills` field, and no
card has ever set one. **There is no S3 skill behaviour to evaluate — the mechanism has never
been exercised once.** D3's index work and D6's suite-reachability rule both apply to S1/S2 only.

**The gateway is degraded, not merely idle.** `hermes-gateway` has burned **~7,074 s of CPU**
since its 2026-08-17 start, and its 30-day journal is effectively one repeating
`ClientConnectorDNSError` against `gateway-us-east1-d.discord.gg` (53 unhealthy warnings in 30d,
14 in 7d) — a Discord *gateway* connection for a surface `CLAUDE.md` documents as delivery-only
via `bin/deliver_report.sh`, which is REST and does not need it. So the running cost buys a
connection nothing consumes. (Note: a naive `grep -vci discord` counts 526 "non-Discord" lines,
but those are traceback frames of the same errors — the word does not appear in a frame. Do not
propagate that number.)

**Two same-named objects; only one is being retired.** `hermes` the **CLI**
(`~/.local/bin/hermes`) is load-bearing — `bin/local_tier_eval.sh:105` execs it
(`timeout "${TIMEOUT_MIN}m" "$HERMES" -t "$toolset" -z "$prompt"`) for the local-tier eval, and a
live `hermes` process in the process table is what caught this. `hermes-gateway` the **daemon**
owns the kanban board and nothing scheduled. **Retirement touches the daemon and the board only;
`~/.local/bin/hermes` and `local_tier_eval.sh` are not in scope.** Same trap as D8's three unit
trees: a correct verdict about a same-named object hides the real one.

*Method note:* my first grep classified `local_tier_eval.sh` as a path-only reference, because it
invokes `"$HERMES"`, not a literal `hermes `. A classifier that only matches literal invocations
under-reports every `$VAR` caller — re-run any such sweep for variable forms before trusting it.

**The kanban dispatch path is dead code, and one measurement nearly said otherwise.**
`content-change-dispatch`'s journal shows the kanban runtime command and its timer is active,
enabled and firing every 15 minutes — on a workflow re-enabled today (registry §7.4). That looked
like a live dependency. Three measurements disproved it: the kanban path last actually ran
**2026-08-13**; today's ticks short-circuit at `bin/content_change_dispatch.sh:71` ("no new Picked
rows … refreshing state, no dispatch"); and both content triggers share the same override file
(`bin/content_change_dispatch.sh:25` and `systemd/augustus-content.service:11` →
`~/.config/agent-workforce/augustus-content.env`), whose live `AGENT_RUNTIME_CMD` is
`run_content_via_buzz.sh`. **A green timer on a dead code path is exactly the D8/readiness class
of false signal** — the journal line was a stale artefact of the override, not evidence.

**Dead code the retirement removes:**
- `bin/kanban_run_and_wait.sh`
- `bin/agent_propose.sh:267-270` — the `*kanban_run_and_wait.sh*)` branch setting
  `max_attempts=1` (with the `retries: 1` intent it encodes migrating to the workflow's own
  manifest if any surface still needs it)
- `profiles/standing_research.env.example:34` — already commented out
- `tests/test_kanban_run_and_wait.sh` and `tests/test_kanban_crash_not_benign.sh` — **the first
  two orphans found under D6's reachability rule.** They pass today and prove nothing, which is
  precisely the failure D6's rule exists to catch. Delete with the code, in the same commit.

**Retirement sequence — order matters, and step 1 is not optional.**
1. **Move the 5 blocked SEO cards off the board first.** They are the only content on it that is
   not a completed record, they have been blocked 53 days, and retiring the board loses them.
   Destination: the `vpc-seo` work already tracked in the Vantage SEO remediation task list.
   **Do not proceed to step 2 until they are somewhere durable.**
2. Export the board (all 11 cards) to `design/archive/` as a plain record — it is the only
   evidence of what S3 ever did.
3. `systemctl --user disable --now hermes-gateway`, **leave it installed but stopped** for one
   review cycle. Reversible; ends the CPU burn and the DNS retry loop immediately.
4. Remove the dead code and its two suites (one commit, `verify.sh` green).
5. Drop S3 from `design/agent-model.md` §2's surface table and from the manifests' `surface`
   enum, leaving S1/S2/S4. Record it as retired-with-date, not deleted from the history.

**Consequences elsewhere in this design:**
- **D3 (c) — "should S3 cards select skills?" — is answered NO by retirement**, not by design
  preference. The `skills:` field goes with the board.
- `design/agent-model.md:113` records `skills = 25 # kanban only: offered count, measured`. That
  field belongs to a surface that is going away; fold the measured 25 into the S1/S2 discussion
  where it is actually true, and drop the kanban qualifier.
- **D9 inherits a smaller problem:** three surfaces to cover rather than four.

**One thing this does NOT do:** it does not retire `hermes` the CLI, `~/.hermes/profiles/`, or the
episodic-memory path. Those are entangled with the `AGENT_PROFILE` naming defect (six scheduled
jobs logging `memory=no-store`) which is registry §6.6 work, and must not be bundled in here.

---

### D8 — Add a source-vs-deployed drift assertion to `bin/verify.sh`?
*(D3 §8.3)*

`verify.sh` grades the source tree; every other eval layer grades the deployed one. So a
green gate says nothing about what is running. **Two of D2's eight gaps were exactly this
defect** (§6.2 throttle, §6.3 unit drift).

- **Recommend:** yes. Highest-yield single check available.

**ANSWER (2026-09-01): YES — one script, three callers. Drift was worse than recorded, and bidirectional.**

Measured before deciding. Both halves had live drift, in opposite directions:

**Units (`systemd/` vs `/etc/systemd/system/`).** Three units carried
`OnFailure=agent-alert@%n.service` in `/etc` and **not** in the source unit here —
`bd-stall-radar`, `m1-signal-scan`, `weekly-pre-assembly`. Any redeploy from source would have
silently removed alerting from three units and nothing would have gone red. Backported in
`e0e4b25`; all 47 source units are now byte-identical to `/etc`. **That is CONTENT drift only —
see the existence correction below.**

**Code (`bin/` vs `~/agent-workforce/bin/`).** Three files stale on the box and two never
deployed at all:

| file | drift | deployed copy dated | reaches |
|---|---|---|---|
| `agent_inbox_notion_sync.py` | **220 lines** | 2026-08-11 | `agent-inbox-sync`, `inbox-backlog-alert`, `overnight-pre-snapshot` |
| `ops_page_publish.py` | 46 lines | 2026-07-23 (**6 weeks**) | `ops-view.sh` |
| `notion_daily.py` | 24 lines | 2026-07-27 (5 weeks) | daily-rhythm Notion idempotency |
| `agent_inbox_branch_rows.py` | never deployed | — | called by `agent_inbox_notion_sync.py` |
| `notion_markdown.py` | never deployed | — | — |

NUC-44 recorded this tree falling "6 days behind". It reached **six weeks**, and today's
branch-rows work was committed to git and not running.

**The finding that shapes the design: drift is bidirectional, and one direction is invisible
to a commit-time check.** The three `OnFailure` lines were never committed by anyone — someone
edited `/etc` by hand and the source never learned. A gate that only runs when a human commits
cannot see that class at all. That is why the timer caller is not optional; it is the only one
that catches it.

**Shape:**

- `bin/check_deploy_drift.sh` owns the comparison, once. Compares `bin/` against
  `~/agent-workforce/bin/`, and `systemd/*.{service,timer}` against `/etc/systemd/system/`.
  Ignores `__pycache__/` and `*.bak*`. Exits 1 on any differing or missing file.
- `bin/verify.sh` calls it as a **hard fail** — you cannot commit a source change while the box
  runs something else.
- `bin/deploy` calls it as a **post-condition** — a deploy that did not converge is a failed
  deploy, not a quiet one.
- A daily timer calls it — the `/etc`-hand-edit case above.

**Trap the script must not fall into: only one unit comparison against `/etc` is
meaningful.** Source `systemd/`, the deployed staging copy `~/agent-workforce/systemd/`, and
live `/etc/systemd/system/`. **`bin/deploy` writes the staging copy and never writes `/etc`** —
its own output says so ("systemd services exec from the runtime tree"), and the deployed-copy
memory note records the same. So a check comparing source against the *staging* copy goes green
the moment a unit is deployed, while `/etc` stays stale — a false green in precisely the
direction that matters. Compare `systemd/` to `/etc` directly.

**BUILT 2026-09-02 (brief 2). Three corrections to the shape above, all measured:**

- **There are FOUR unit trees, not three.** `~/.config/systemd/user/` is never mentioned above
  and held **nine** units with no source counterpart in this repo — `buzz-agent@.service`,
  `buzz-notion-broker.service`, `buzz-pr-watch.{service,timer}`, `hermes-gateway.service`,
  `nekovri-subsidy-{kickoff,watchdog}.{service,timer}`. That is the whole Buzz fleet's unit
  layer, including the file brief 1 edited on 2026-09-01 to add `CLAUDE_CODE_EXECUTABLE`. They
  now have a source home at `systemd/user/`, and the check compares it as a third pair.

- **Content drift was the cheap half; EXISTENCE drift is the expensive one, and the shape
  above only specified content.** "Exits 1 on any differing or missing file" reads as covering
  it, but a set-difference has two directions and only one of them was being taken: `/etc`-only
  (a rebuild from source loses the unit) and source-only (the box is not running what the repo
  says). Both are red now. The chain that makes the first direction expensive: no source =>
  `bin/backup_config.sh:17` cannot enumerate it => it is in no tarball => the rebuild checklist
  restores `/etc` from the tarball and `systemd/` => the unit is gone, and nothing anywhere
  reports its absence.

- **Ownership needs a declaration, and it must fail closed.** A bare set-difference returns OS
  units. Restricting to regular `*.service`/`*.timer` files drops the 8 OS symlinks and the 6
  `*.bak*` files, leaving exactly `ollama.service` — but "unknown => ignore" is R12's defect
  class, so the answer is `design/unit-ownership.toml` (permanent) plus the manifests'
  `status = "campaign"` + `expires` (dated), READ from the manifests rather than re-keyed. No
  heuristic decides ownership: the obvious one, "references `/home/dave`" or "`User=dave`",
  misclassifies `systemd/ttm-pool-drain.service`, which is ours and has neither.

- **A unit file cannot carry its own drift commentary — the comment IS drift.** The stale
  "/etc-only scaffolding" line in `systemd/praetorium-phaseb-brief@.service` was wrong after
  `d72f562` committed all six, and correcting it in place made the file differ from `/etc` for
  a comment, turning a green byte-identity assertion red and requiring a `sudo` install to
  clear — the note asserting "source and /etc are byte-identical" falsified itself by
  existing. Unit prose belongs where nothing compares bytes. Recorded here instead: **the
  phaseb-brief trap moved rather than closed.** They pass today; on the day they are removed
  from `/etc` they become source-only, which is the same defect in the other direction. Delete
  from BOTH trees or neither, and note no brief in the queue currently owns that cleanup.

**Method note, and it is this decision's own lesson turned on itself:** `e0e4b25` backported
three `OnFailure` lines and declared all 47 source units byte-identical to `/etc`. That was
true, and it was a cleared baseline for CONTENT only — existence drift went unmeasured on both
sides of it, and a whole tree went unnamed. A cleared baseline is only cleared for the property
you compared.

**Baseline cleared 2026-09-01 for CONTENT drift only — CORRECTED while measuring D5.** `bin/deploy`
run with Dave's approval: 5 `bin/` files plus the profile/config archives. Post-deploy both halves
measure zero *content* drift, so the file-comparison half **ships green**
rather than red-on-arrival — unlike D6's coverage checker, which ships red with four named holes
by design.

**But EXISTENCE drift was never measured, and it is not clear.** A unit present in one tree and
absent from the other is invisible to a byte-comparison of the units that exist in both — which is
all `e0e4b25` and the deploy checked. Measured 2026-09-01, **three agent-workforce units live only
in `/etc` with no source counterpart**:

- `fleet-turn-check.timer` / `.service` — the hourly gate that proves an agent can complete a turn,
  and the one signal that stayed honest through a 4-day outage. **It exists nowhere in this repo.**
  A rebuild from source loses it silently.
- `praetorium-content-strategy-research.timer` / `.service` and
  `praetorium-faceless-content-research.timer` / `.service` — the two campaign units of D5.

So `bin/check_deploy_drift.sh` must compare **membership as well as content**, in both directions,
and it does **not** ship green: it ships red naming `fleet-turn-check` at minimum. Two design
consequences: the check needs an **ownership filter** (a bare set-difference against
`/etc/systemd/system/` also returns `chronyd`, `ollama`, `iscsi` and every other OS unit — 15 in
total, 12 of them not ours), and it needs an **explicit, dated exclusion list** for genuinely
ephemeral units, so a campaign timer can be `/etc`-only on purpose without teaching everyone to
ignore a red. Backport `fleet-turn-check` before the check lands; exclude the campaigns and delete
them per D5.

**Method note:** the content half was measured and cleared, which made the whole question feel
answered. The dimension nobody measured was the one that can lose a unit outright. A cleared
baseline is only cleared for the property you compared.

- **Dependencies:** none. Independent of D6.

---

### D9 — Negative tests for `enforced = true` must-not rules?
*(D3 §8.4)*

The manifests carry 22 must-not rules; only some are `enforced = true`. An unenforced rule
is prose, and prose is what D2 §6.1 found sitting between the fleet and a live
`send_message`. A negative test fails if the mechanism is removed.

- **Depends on:** D1 — the deny-list is the mechanism these tests would assert.
- **Recommend:** yes, scoped to the outward-action rules only.

**ANSWER (2026-09-01): YES — but the stated scope is almost empty, and the one rule it does
yield is weaker than its own flag claims. Widen the scope, and sequence it behind D1.**

**"Scoped to the outward-action rules only" selects exactly one rule.** Counted across the five
manifests: **22 must-not rules, 6 `enforced = true`, 8 outward-action — and the intersection is 1.**

| | outward rule | manifest | enforced |
|---|---|---|---|
| | send email or any outward message | marcus, claudius, augustus (×3) | **false** |
| | execute anything — no writes, no commits, no sends | aurelian | **false** |
| | call `buzz messages send` outside `bin/deliver.sh` | augustus | **false** |
| | run `publish_boxsafe.sh` | trajan | **false** |
| | use `--no-verify` on any push | trajan | **false** |
| ✔ | **push the vault `main` branch** | trajan | **true** |

So the recommendation as written buys one test. **That is not a gap in the plan — it is the
finding.** D2 §6.1 said prose sits between the fleet and a live `send_message`; these seven
`false`s are that same fact, stated honestly in the manifests. They cannot be tested because
there is nothing yet to test. **D1 is what converts them**, which makes the dependency line above
backwards: D9 does not merely *depend on* D1, it is **the assertion half of D1** and should be
written in the same brief, not a later one.

**And the one enforced rule is over-flagged.** Measured:

- The guard is `00_system/tools/hooks/pre-push`, installed **per clone, by hand**
  (`install_vault_hooks.sh` — "install the main-push guard into **this clone's** `.git/hooks`").
- It is installed in `~/dev/Obsidian_AI_Operating_System/` (3,569 B, 2026-08-15) and **absent from
  `~/dev/obsidian-ai-os-boxsafe/`** — that clone has no hooks at all, sits on `main`, has a live
  push remote (`git@github-boxsafe:…`), and the box holds `keys/boxsafe_deploy`. **It is also the
  clone `~/vault` resolves to.**
- The installer's own header disclaims the flag: *"what it does not do is documented in
  hooks/pre-push; it is not protection for main."* It records a supervised push; it does not
  prevent an unsupervised one.
- It is bypassable by `--no-verify` — **which is itself a separate must-not rule, `enforced = false`.**
  An enforcement mechanism whose bypass is guarded only by prose is prose with extra steps.

`enforced = true` here means "a mechanism exists somewhere", not "the mechanism covers every path
the rule names". **First test: assert the guard is installed in every vault clone on this box that
has a push remote. It ships RED.**

**The design constraint that governs every one of these tests, and must be stated before anyone
writes one: a negative test asserts the ABSENCE OF CAPABILITY. It never attempts the forbidden
action.** You cannot test "must not send email" by sending email — the test would *be* the
violation, and a "safe" test recipient is still an outward action from a box whose whole charter
is that it performs none. Every test here is therefore an assertion about the *state of a
mechanism* (a config key, an installed hook, an absent credential, a namespace that lacks a path),
never about behaviour under attempt.

That constraint also fixes what the field is allowed to mean. **Redefine: `enforced = true` iff a
machine-checkable artifact exists whose removal or absence a test can detect.** Under that
definition the vault-push rule is `true` only once the guard covers both clones; today it is
aspirational.

**Scope decided: all 6 currently-enforced rules, plus each outward rule as D1 promotes it.**

| test | asserts | today |
|---|---|---|
| vault push guard | `pre-push` guard installed in every vault clone with a push remote | green — boxsafe hooked 2026-09-01 |
| aurelian unaddressable | `aurelian` absent from `bin/buzz_agents.env` | green (0 matches) |
| propose write boundary | `agent_propose.sh` confines writes to `_inbox/agents/**` (marcus + claudius, one test) | green |
| augustus no-fetch | the bwrap wrapper leaves no usable `~/.ssh`, so `git fetch` cannot succeed | green |
| outward connectors denied | the four `mcp__claude_ai_*` families are in the agent-session `permissions.deny` | green — D1 landed 2026-09-01 |
| hermes cron empty | trajan's rule | **fold into D7's retirement, not a standing test** |

**Two structural notes for the brief.**

1. **These tests belong to the fleet, not to a workflow — and D6's checker cannot express that.**
   D6 resolves each *workflow* to a suite via a declared join. A guard suite that asserts a
   fleet-wide invariant has no owning workflow, so D6's reachability rule would classify it as an
   **orphan and flag it for deletion** — the same verdict it correctly gives the two kanban
   suites. D6's declared-join schema needs a `fleet` owner value before this suite lands, or the
   first thing the coverage checker does is recommend deleting the security tests. **This is a
   required amendment to D6, not a nice-to-have.**

2. **Most of what these tests assert lives outside this repo** — `~/.claude/settings.json`, a
   `.git/hooks/` file in two other repos, a bwrap wrapper in `/usr/local/bin`. That is the same
   cross-boundary pinning that silently rotted augustus's `sed` ranges in D3: this repo's commits
   cannot see those files move. The difference is that a test *is* the gate the line-pins never
   had — it fails loudly when the far side changes. So the boundary is acceptable here **provided
   every assertion is a test and none is a comment.** No negative rule gets recorded as a note.

`bin/verify.sh` already collects `tests/*.sh`, so these are picked up with no gate change.

---

## Carried work — decided in principle, not done

Not questions. W1-W5 are D1's: it settled the direction and nobody implemented them.
W6-W10 were opened by Phase-B briefs 2-4 (2026-09-02) — four of them are things those
briefs deliberately did not do, and W6 is the one that keeps the gate red.

| | Item | Source | Note |
|---|---|---|---|
| W1 | Episodic memory keys on the OWNER persona, not the runtime profile name | D1 §6.2, §6.6 | No scheduled persona workflow accumulates episodic memory today. Fleet-wide rename, six jobs. |
| W2 | Every persona workflow's profile states its owner in one standard header line | D1 §6.3 | daily-plan/eod say "You are Marcus"; the `_cc_task` variants are persona-less. |
| W3 | Generate the reporting jobs' unit lists from the registry | D1 §6.4 | The `praetorium-*` glob defect exists in six files; 8 timers are invisible to every report. |
| W4 | Consolidate the two job-override example homes | D1 §6.5 | Stale directory archived 2026-09-01; the consolidation itself is not done. |
| ~~W5~~ | ~~Every workflow entry carries an explicit `status`~~ | D3 §5 R15 | **DONE 2026-09-01 (`3a52d42`)** — all 26 entries carry one, and all 26 carry `suite` or `suite_exempt` (R15b, `6e4fb34`). Recorded done at line 571 and in `eval-spec.md` §5; this row was the one stale copy. D6 unblocked and built. |
| W6 | Four standing workflows name no suite, and one suite has no owner | D6, brief 3 | **THE PR GATE BLOCKER.** `m1-signal-scan`, `overnight-morning-report`, `agent-workforce-auto-sync`, `overnight-pre-snapshot` carry `status = "standing"` with neither `suite` nor `suite_exempt`; `tests/test_content_inbox_finalize.sh` is claimed by no workflow and no fleet owner. Brief 3 shipped red on exactly these five by design (its criterion 11) — but **no brief in the queue closes them**, so `bash bin/verify.sh` cannot go green and every PR on this branch is red. Each needs a suite or a named `suite_exempt` reason; the orphan needs an owner or deletion. |
| W7 | The drift check compares 2 of the 8 paths `bin/deploy` ships | D8, briefs 2+4 | `bin/deploy:20` ships `bin profiles docs CLAUDE.md AGENTS.md README.md config systemd`; `bin/check_deploy_drift.sh` compares `bin` and the three unit trees. **`profiles/` is the gap that has already bitten**: brief 4 fixed `augustus_content_task.md`, the runtime copy still carries the pinned line ranges, and the drift check says nothing about it — it flags the undeployed `bin/skill_sections.sh` beside it, so the deploy is not missed *this* time, but a profile-only change would land silently. Same defect class D8 exists to close, one tree over. |
| W8 | The six `praetorium-phaseb-brief@*` units have no cleanup owner | D8, brief 2 | They pass today (source and `/etc` byte-identical). On the day they are removed from `/etc` they become source-only, which is the same defect in the other direction. **Delete from BOTH trees or neither** — and no brief in the queue sequences that. D5's cleanup covers the two campaign families only. |
| W9 | `design/fleet-suites.toml`'s `asserts` list has no join to the assertions it names | D6, brief 1 | The six `asserts` strings and `tests/test_workflow_coverage.sh`'s six `check <id>` calls are related by convention only: `test_workflow_coverage.py` reads `path` and `owner` and never `asserts`, and `test_fleet_guards.sh` only checks the list is non-empty. Renaming an id in one place leaves the other silently stale — one fact in two places, which is the class D6 exists to detect. Raised by review 2026-09-02 and deliberately not fixed inside brief 4: it predates that work and joining it properly is its own change. |
| W10 | Two bespoke off-box predicates, neither able to use `box_only_with` | brief 2, brief 4 | `bin/check_deploy_drift.sh` and `tests/test_content_skill_extract.sh` each hand-roll a guard whose predicate is "this is not Praetorium", because `box_only_with` means "skip if a path is absent" — the opposite of what both need, which is a **missing subject on the box staying RED**. Raised by review 2026-09-02 and declined there: a shared helper would have to span `bin/` ↔ `tests/`, and the naive consolidation costs the fail-closed property. If a third site appears, that is the signal to design the helper properly rather than copy it again. |


### Pending actions reserved for Dave — the branch cannot clear these itself

Not carried work; three concrete steps this box will not take from an unmerged branch. Every
one is currently reported by `bin/check_deploy_drift.sh`, so none of them can be forgotten
silently — but none clears until someone runs it.

1. **`bin/deploy`, after merge.** Seven `bin/` files are source-only or content-drifted,
   including `check_deploy_drift.sh` itself and `skill_sections.sh`. **Until this runs,
   augustus reads the skill by the old pinned line ranges** (brief 4) — the runtime profile
   still carries them.
2. **`sudo` install of `agent-drift-check.{service,timer}`.** Written to `systemd/`, absent
   from `/etc`. Note the unit's `ExecStart` names the SOURCE repo, not the runtime tree, and
   that inversion is deliberate — see the unit header.
3. **Verify by RUNNING the job, not by `list-timers`.** `active` + `enabled` +
   a correct `next_elapse` say nothing about whether `ExecStart` exists.

---

## Phase-B brief order

The original order was for *answering*; this one is for *building*. It differs in three places,
each forced by something an answer found.

1. **D1 + D9 as ONE brief.** D9 is the assertion half of D1, not a later item: seven of the eight
   outward must-not rules are `enforced = false` precisely because D1's mechanism is not installed
   yet. Installing the deny entries and writing the tests that fail when they are removed is one
   unit of work; splitting it ships a mechanism nobody checks. **Amend D6's declared join with a
   `fleet` owner value first, or its checker's first act is to flag the new security suite as an
   orphan.**
2. **D8's drift check, widened.** It must compare unit *membership* as well as content, in both
   directions, with an ownership filter and a dated exclusion list. It ships **red**, naming
   `fleet-turn-check` — which exists only in `/etc` and would be lost by any rebuild from source.
   Backport that unit as part of the brief.
3. **W5 → D6** — the coverage checker, once its schema carries `fleet`.
4. **D3, both parts.** Part 1 (heading-anchored extraction + its test) is the live defect and
   should not wait on part 2 (pointer skills), which is independent.
5. **D7's retirement**, in the recorded sequence — the 5 SEO cards move off the board **first**.
   Folds in trajan's `hermes cron` negative test, which becomes moot rather than standing.
6. **W1–W4**, then **D5's cleanup**: delete the two campaign `/etc` units after their last
   firings (content-strategy 09-03 23:00, faceless 09-04 01:30).

**D4, D2 and D5 need no brief** — D4 and D2 were resolved as decisions, and D5 was a "no".

**Standing side items, owned by nobody yet:** marcus's engram is at ~79% of the 65,535 B wall and
needs a prune; `augustus-content.timer` was found *stopped* and ran once in eight days — confirm it
holds its own schedule before anything is concluded from the content backlog.
