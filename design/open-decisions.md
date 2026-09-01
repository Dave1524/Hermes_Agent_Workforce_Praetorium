# Open decisions — the sync agenda before Phase B

**Status:** open, 2026-09-01. This is the single list. D1 is closed; D2 and D3 each end in
a decisions section, and this file consolidates what is still unanswered plus the work D1
decided in principle but never implemented.

**How to use it:** answer inline in CAPS under each item, the same way D1 §7 was closed.
That worked — the answers stayed attached to the evidence instead of living in a chat
scrollback. Nothing in Phase B starts until D1–D9 are answered.

---

## Where each session landed

| | Doc | Decisions | State |
|---|---|---|---|
| D1 | `workflow-registry.md` | 8 | **all closed** 2026-09-01 (`ed568f8`) |
| D2 | `agent-model.md` §8 | 5 open + 1 withdrawn | open |
| D3 | `eval-spec.md` §8 | 4 | open |

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

**ANSWER:**

---

### D2 — Fix the alert throttle now, or fold it into a Phase-B brief?
*(D2 §8.3, covering §6.2 and §6.3)*

§6.2: the failure-alert throttle has been deployed-but-unwired for 18 days. `bin/deploy`
copied the script; nobody wrote `/etc`. 19 of the last 60 alert lines are the same
`qmd-refresh` message. §6.3: three repo unit files are *behind* `/etc`, and four live units
have no repo source at all.

- **Recommend:** fix §6.2 now — it is degrading alerting today. Fold §6.3 into Phase B.
- §6.6 (per-workflow locks) and §6.7 (import the four orphan units) are Phase B either way.

**ANSWER:**

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

**ANSWER:**

---

### D4 — Is the manifest the source of truth?
*(D2 §8.5)*

i.e. may Phase B generate each wrapper's `--allowedTools` from `design/agents/*.toml`
rather than the reverse. This is the load-bearing one: it decides whether the manifests are
documentation or configuration. Everything in D3's coverage checker assumes the former is
false.

- **Recommend:** yes.

**ANSWER:**

---

### D5 — Do you want a *standing* content-research workflow?
*(D2 §8.6 — replaces the withdrawn timer-fix decision)*

The two campaigns end 09-03 and 09-04 having delivered ~8 runs each on two named topics.
A permanent version is a different thing: it needs topic rotation, a slot that is not 01:30
(the `augustus-content` lock collision of §6.6), and its own registry row.

- **Recommend:** no for now. Let them expire; revisit when the content pipeline's existing
  backlog is consumed.

**ANSWER:**

---

### D6 — Build the workflow-coverage checker as the first Phase-B item?
*(D3 §8.1)*

9 of 26 workflows have a suite that owns them. Nothing on the box can report that, because
no layer knows the workflow list — the manifests are the first artifact that does. The
checker reads `design/agents/*.toml`, resolves each live workflow to a suite, and fails on
an unowned one.

- **Depends on:** W5 (explicit per-workflow `status`), and on D4 being yes.
- **Recommend:** yes. It is small, and it grades every brief that comes after it.

**ANSWER:**

---

### D7 — Leave the Hermes kanban surface unevaluated?
*(D3 §8.2)*

Nothing grades a kanban card's execution. This may be correct — but it should be a decision
rather than an omission.

- **Recommend:** yes, leave it; fold into D3 (skills posture) rather than answering twice.

**ANSWER:**

---

### D8 — Add a source-vs-deployed drift assertion to `bin/verify.sh`?
*(D3 §8.3)*

`verify.sh` grades the source tree; every other eval layer grades the deployed one. So a
green gate says nothing about what is running. **Two of D2's eight gaps were exactly this
defect** (§6.2 throttle, §6.3 unit drift).

- **Recommend:** yes. Highest-yield single check available.

**ANSWER:**

---

### D9 — Negative tests for `enforced = true` must-not rules?
*(D3 §8.4)*

The manifests carry 22 must-not rules; only some are `enforced = true`. An unenforced rule
is prose, and prose is what D2 §6.1 found sitting between the fleet and a live
`send_message`. A negative test fails if the mechanism is removed.

- **Depends on:** D1 — the deny-list is the mechanism these tests would assert.
- **Recommend:** yes, scoped to the outward-action rules only.

**ANSWER:**

---

## Carried work — decided in principle, not done

Not questions. D1 settled the direction; nobody has implemented them.

| | Item | Source | Note |
|---|---|---|---|
| W1 | Episodic memory keys on the OWNER persona, not the runtime profile name | D1 §6.2, §6.6 | No scheduled persona workflow accumulates episodic memory today. Fleet-wide rename, six jobs. |
| W2 | Every persona workflow's profile states its owner in one standard header line | D1 §6.3 | daily-plan/eod say "You are Marcus"; the `_cc_task` variants are persona-less. |
| W3 | Generate the reporting jobs' unit lists from the registry | D1 §6.4 | The `praetorium-*` glob defect exists in six files; 8 timers are invisible to every report. |
| W4 | Consolidate the two job-override example homes | D1 §6.5 | Stale directory archived 2026-09-01; the consolidation itself is not done. |
| W5 | Every workflow entry carries an explicit `status` | D3 §5 R15 | Manifest edit, not code. Blocks D6. |

---

## Suggested order

Dependencies first, then yield.

1. **D4** — decides whether the manifests are configuration. Everything downstream assumes it.
2. **D1** — closes a live outward-action exposure and unblocks D9.
3. **D2** (§6.2 half) — stops the alert degradation running today.
4. **W5 → D6** — makes coverage self-reporting instead of a number that rots.
5. **D8** — the drift assertion; retires the class that produced two of D2's gaps.
6. **D3 + D7 together** — one skills-and-kanban conversation, not two.
7. **D5**, then **D9**, then **W1–W4** as Phase-B briefs.

Items 1–3 are conversations. 4–7 are briefs.
