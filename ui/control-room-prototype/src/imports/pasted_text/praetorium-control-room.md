Create a polished, responsive internal operations web application called “Praetorium Control Room.”

  This is not a marketing website and not a generic analytics dashboard. It is a calm, exception-first control surface for one operator, Dave, who manages approximately 30 automated AI workflows running on a
  private Linux server called the Praetorium box.

  The application should help Dave answer immediately:

  1. Are my workflows healthy?
  2. Which runs are incomplete or require action?
  3. Which agents and workflows are consuming tokens and cost?
  4. What did each workflow produce, and can I open that output quickly?
  5. Why did a workflow run, especially a research workflow?
  6. Can I safely pause, resume, run, retry, stop, change or retire it?

  Build a functional, interactive desktop-first prototype at 1440px width, responsive down to tablet width. It is hosted privately on the Praetorium box and used only by Dave, so do not create onboarding, account
  management, billing or multi-user administration.

  INFORMATION ARCHITECTURE

  Use a persistent left sidebar with:

  - Overview
  - Workflows
  - Incidents
  - Usage
  - Activity

  At the bottom of the sidebar, show:

  - “Praetorium box”
  - Connected/healthy indicator
  - Last data refresh
  - “Private · Local” label

  Use a compact top bar with page title, global workflow search, last refresh time and Refresh button.

  SCREEN 1 — OVERVIEW

  Make this the default landing page. It should be exception-first: healthy workflows should recede visually while problems and decisions stand out.

  At the top, show compact status summary cards:

  - 30 workflows
  - 24 healthy
  - 2 running
  - 2 need attention
  - 2 paused

  Include icons and text labels; never rely on color alone.

  The main, most prominent panel is “Needs attention.” Show incident rows containing:

  - Severity
  - Workflow
  - Agent
  - Plain-language issue
  - How long it has been open
  - Required next action
  - “Investigate” button

  Example incidents:

  - Standing Research · Claudius · Run incomplete: no proposal or valid decline
  - Augustus Content · Augustus · Output created but board transition missing

  Add a “Recent outputs” panel with:

  - Workflow
  - Output title
  - Created time
  - Output status
  - “Open in Notion” primary action
  - Secondary actions: Approve, Reject, Edit, Send, Assign, Postpone, Archive

  Add an “Agent usage” panel showing Marcus, Trajan, Claudius, Augustus and Aurelian. Show input tokens, output tokens, total tokens and cost. Include an honest “Unavailable” state with a tooltip saying “Runtime
  did not provide trustworthy usage data.” Never display missing telemetry as zero.

  Add a compact reliability chart showing valid outputs versus eligible runs over the last seven days. Keep visualization restrained and operational.

  SCREEN 2 — WORKFLOW PORTFOLIO

  Show one row per logical workflow, not one row per technical trigger or systemd unit.

  Provide filters for:

  - Health
  - Agent
  - Lifecycle
  - Output status
  - Trigger type

  Columns:

  - Workflow
  - Owner agent
  - Purpose
  - Health
  - Schedule/trigger
  - Last run
  - Next run
  - Latest output
  - Reliability
  - Token usage
  - Lifecycle

  A logical workflow can have multiple triggers. Show these inside an expandable trigger section rather than duplicating the workflow row.

  Use realistic example workflows:

  - Daily Plan — Marcus
  - Standing Research — Claudius
  - Knowledge Digest — Claudius
  - Augustus Content — Augustus
  - Agent Workforce Auto Sync — Trajan
  - Fleet Evaluation — Trajan

  Status vocabulary:

  - Healthy
  - Running
  - Incomplete
  - Failed
  - Paused
  - Unknown

  SCREEN 3 — WORKFLOW DETAIL

  Create a detailed workflow page.

  Header:

  - Workflow name and agent
  - Health badge
  - Human-readable purpose
  - Primary “Open latest output” button
  - Controls: Pause or Resume, Run now, Retry, Stop
  - Overflow menu: Change schedule, Retire workflow

  Under the purpose, show a sentence in this structure:

  “When [trigger] occurs, this workflow produces [artifact] for [beneficiary], so they can [next action].”

  Create summary cards for:

  - Last run
  - Next scheduled run
  - Seven-day reliability
  - Token usage
  - Cost
  - Outputs used

  Add sections for:

  1. Triggers and schedules
  Show all triggers, timezone, eligibility rules and whether catch-up is enabled.

  2. Latest output
  Show output title, freshness, Notion destination and available human actions.

  3. Recent runs
  Show outcome, duration, assertions, tokens, cost and artifact link.

  4. Benefit evidence
  Show reliability and four separate consumption signals:
  - Opened
  - Approved
  - Sent or published
  - Manually marked useful

  Do not combine these into one opaque “engagement score.”

  RESEARCH WORKFLOW LINEAGE

  For the Standing Research workflow, include a prominent visual lineage:

  Candidate sources
  → Selection criteria
  → Selected topic and reason
  → Schedule or triggering event
  → Claudius research run
  → Notion proposal
  → Dave’s next action

  Every stage should be selectable to reveal its evidence. The design must make it obvious why a particular research topic started and how it was selected.

  RUN AND AGENT-HANDOFF DETAIL

  Create a run-detail drawer or page containing a vertical event timeline.

  Demonstrate a headless interaction between Marcus and Trajan:

  - 09:02 · Marcus requested an infrastructure diagnosis
  - 09:02 · Trajan accepted the handoff
  - 09:03 · Trajan working
  - 09:08 · Verification completed
  - 09:09 · Trajan replied
  - 09:09 · Artifact and evidence attached
  - 09:10 · Marcus marked the handoff complete

  Display parent and child run IDs, timestamps, duration, outcome and artifact links. This should provide visibility without requiring Buzz Desktop. Show bounded summaries rather than entire private prompts.

  CONTROL INTERACTIONS

  Make the controls interactive and design the confirmation states carefully.

  Pause:
  - Explain that future scheduled runs will stop.
  - State clearly: “The current run will be allowed to finish.”
  - Provide Cancel and Pause workflow actions.

  Resume:
  - Show the next scheduled run.
  - Warn if systemd catch-up may immediately start a missed run.

  Run now:
  - Show workflow, expected output and estimated operational effect.
  - Return a visible run ID after confirmation.

  Retry:
  - Only enable when the workflow contract declares retry safe.
  - Explain why Retry may be unavailable.

  Stop:
  - Use a destructive confirmation dialog.
  - Require a reason.
  - Explain what partial artifacts may remain.

  Change schedule:
  - Do not apply the change directly.
  - Show current and proposed schedule, timezone and catch-up behavior.
  - Primary action: “Create reviewed PR.”

  Retire:
  - Show affected schedules, runners, contracts and routes.
  - Require a reason.
  - Primary action: “Create retirement PR.”
  - Never present retirement as an immediate toggle.

  INCIDENTS AND BUZZ

  Create an Incidents page with Open, Acknowledged and Resolved tabs.

  Each incident shows:

  - Workflow and agent
  - Failed assertion or incomplete state
  - First seen and last seen
  - Required human action
  - Related run
  - Artifact/log links
  - Buzz notification state

  Include settings indicating:

  - Immediate Buzz notification only when Dave must act
  - Repeated observations are deduplicated
  - One daily digest contains unresolved incidents
  - A recovery message is sent when an incident closes

  VISUAL DIRECTION

  Create a serious, quiet operations cockpit—not sci-fi, cyberpunk or a stock admin template.

  Use:

  - Deep charcoal and warm graphite surfaces
  - Off-white primary text
  - Muted slate secondary text
  - Restrained brass/amber accent for the Praetorium identity
  - Green for healthy
  - Blue for running
  - Amber for incomplete or attention required
  - Red only for failed or destructive actions
  - Gray for paused and unknown

  Use a highly legible sans-serif such as Inter for interface text and a restrained monospace font for run IDs, timestamps and technical evidence.

  Use generous spacing, clear hierarchy, compact data tables, subtle borders and minimal shadows. Avoid excessive gradients, glass effects, giant KPI numbers and decorative charts.

  Make all states accessible and understandable without color. Include hover, selected, focus, loading, empty, unavailable and error states.

  PROTOTYPE BEHAVIOR

  Use realistic demo data and mark it as demo data. Make navigation, filters, expandable triggers, workflow selection, output actions, confirmation dialogs, incident acknowledgement and the Marcus-to-Trajan
  timeline interactive.

  The final result should feel like a trusted operating instrument: quiet when everything is healthy, unmistakably clear when Dave owes a decision or action.
