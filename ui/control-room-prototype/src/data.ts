export type Health = "healthy" | "running" | "incomplete" | "failed" | "paused" | "unknown" | "attention";
export type Lifecycle = "active" | "paused" | "retired";

export interface Workflow {
  id: string;
  name: string;
  agent: string;
  purpose: string;
  health: Health;
  schedule: string;
  trigger: string;
  lastRun: string;
  lastRunTimestamp: string;
  nextRun: string;
  latestOutput: string;
  latestOutputStatus: string;
  reliability7d: number;
  eligibleRuns: number;
  validOutputs: number;
  tokens: string;
  cost: string;
  lifecycle: Lifecycle;
  retryEnabled: boolean;
  artifact: string;
  notionUrl: string;
}

export interface Incident {
  id: string;
  severity: "high" | "medium" | "low";
  workflow: string;
  agent: string;
  issue: string;
  firstSeen: string;
  lastSeen: string;
  duration: string;
  action: string;
  runId: string;
  status: "open" | "acknowledged" | "resolved";
}

export interface AgentUsage {
  name: string;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  cost: number | null;
  available: boolean;
}

export interface RecentOutput {
  id: string;
  workflow: string;
  title: string;
  createdAt: string;
  status: "approved" | "pending" | "rejected" | "draft";
  notionUrl: string;
}

export interface RunEvent {
  time: string;
  actor: string;
  event: string;
  type: "info" | "handoff" | "working" | "complete" | "artifact";
}

export const WORKFLOWS: Workflow[] = [
  {
    id: "daily-plan",
    name: "Daily Plan",
    agent: "Marcus",
    purpose: "Synthesize a prioritised daily schedule from open tasks, calendar events and standing context",
    health: "healthy",
    schedule: "Daily 07:00 Europe/London",
    trigger: "Cron · daily 07:00",
    lastRun: "2h ago",
    lastRunTimestamp: "2026-09-10 07:02",
    nextRun: "Tomorrow 07:00",
    latestOutput: "Daily Plan · Sep 10",
    latestOutputStatus: "approved",
    reliability7d: 94,
    eligibleRuns: 7,
    validOutputs: 7,
    tokens: "12.4K",
    cost: "$0.09",
    lifecycle: "active",
    retryEnabled: false,
    artifact: "Daily Plan · Sep 10",
    notionUrl: "#",
  },
  {
    id: "standing-research",
    name: "Standing Research",
    agent: "Claudius",
    purpose: "Research a selected topic and produce a structured proposal or a documented decline",
    health: "incomplete",
    schedule: "Tues & Thurs 09:00 Europe/London",
    trigger: "Cron · Tue/Thu 09:00",
    lastRun: "3h ago",
    lastRunTimestamp: "2026-09-10 09:03",
    nextRun: "Thu 09:00",
    latestOutput: "Byzantine fiscal policy — no output",
    latestOutputStatus: "incomplete",
    reliability7d: 71,
    eligibleRuns: 7,
    validOutputs: 5,
    tokens: "48.2K",
    cost: "$0.42",
    lifecycle: "active",
    retryEnabled: true,
    artifact: "Standing Research · Sep 10",
    notionUrl: "#",
  },
  {
    id: "knowledge-digest",
    name: "Knowledge Digest",
    agent: "Claudius",
    purpose: "Curate and summarise notable items from sources read during the week",
    health: "healthy",
    schedule: "Weekly Fri 17:00 Europe/London",
    trigger: "Cron · Fri 17:00",
    lastRun: "Yesterday 17:02",
    lastRunTimestamp: "2026-09-09 17:02",
    nextRun: "Fri 17:00",
    latestOutput: "Knowledge Digest #41 · Sep 9",
    latestOutputStatus: "approved",
    reliability7d: 88,
    eligibleRuns: 4,
    validOutputs: 4,
    tokens: "22.1K",
    cost: "$0.19",
    lifecycle: "active",
    retryEnabled: false,
    artifact: "Knowledge Digest #41",
    notionUrl: "#",
  },
  {
    id: "augustus-content",
    name: "Augustus Content",
    agent: "Augustus",
    purpose: "Draft long-form content and stage it for review before board transition",
    health: "attention",
    schedule: "Daily 11:00 Europe/London",
    trigger: "Cron · daily 11:00",
    lastRun: "5h ago",
    lastRunTimestamp: "2026-09-10 11:00",
    nextRun: "Tomorrow 11:00",
    latestOutput: "Draft #88 · awaiting board",
    latestOutputStatus: "pending",
    reliability7d: 83,
    eligibleRuns: 6,
    validOutputs: 5,
    tokens: "31.7K",
    cost: "$0.28",
    lifecycle: "active",
    retryEnabled: false,
    artifact: "Content Draft #88",
    notionUrl: "#",
  },
  {
    id: "auto-sync",
    name: "Agent Workforce Auto Sync",
    agent: "Trajan",
    purpose: "Reconcile agent configuration files with live system state and flag drift",
    health: "running",
    schedule: "Hourly :00 Europe/London",
    trigger: "Cron · hourly :00",
    lastRun: "12m ago",
    lastRunTimestamp: "2026-09-10 15:00",
    nextRun: "In 48m",
    latestOutput: "Sync #217 · running",
    latestOutputStatus: "running",
    reliability7d: 97,
    eligibleRuns: 24,
    validOutputs: 23,
    tokens: "8.9K",
    cost: "$0.06",
    lifecycle: "active",
    retryEnabled: true,
    artifact: "Sync Report #217",
    notionUrl: "#",
  },
  {
    id: "fleet-eval",
    name: "Fleet Evaluation",
    agent: "Trajan",
    purpose: "Evaluate agent performance across a structured scenario set and surface regressions",
    health: "paused",
    schedule: "Weekly Mon 06:00 Europe/London",
    trigger: "Cron · Mon 06:00",
    lastRun: "8d ago",
    lastRunTimestamp: "2026-09-02 06:04",
    nextRun: "Paused",
    latestOutput: "Fleet Eval #12 · Sep 2",
    latestOutputStatus: "approved",
    reliability7d: 100,
    eligibleRuns: 1,
    validOutputs: 1,
    tokens: "19.3K",
    cost: "$0.16",
    lifecycle: "paused",
    retryEnabled: false,
    artifact: "Fleet Evaluation #12",
    notionUrl: "#",
  },
];

export const INCIDENTS: Incident[] = [
  {
    id: "inc-001",
    severity: "high",
    workflow: "Standing Research",
    agent: "Claudius",
    issue: "Run incomplete: no proposal or valid decline was produced. Contract requires one of the two artifacts.",
    firstSeen: "2026-09-10 09:14",
    lastSeen: "2026-09-10 12:04",
    duration: "2h 50m",
    action: "Review run log, then retry or provide a manual decline.",
    runId: "run-sr-20260910-0901",
    status: "open",
  },
  {
    id: "inc-002",
    severity: "medium",
    workflow: "Augustus Content",
    agent: "Augustus",
    issue: "Output created but board transition is missing. Draft #88 is staged but has not moved to the Review column.",
    firstSeen: "2026-09-10 11:22",
    lastSeen: "2026-09-10 12:04",
    duration: "42m",
    action: "Open the Notion page and manually trigger the board transition, or investigate the API call.",
    runId: "run-ac-20260910-1100",
    status: "open",
  },
  {
    id: "inc-003",
    severity: "low",
    workflow: "Agent Workforce Auto Sync",
    agent: "Trajan",
    issue: "Sync #214 reported a configuration drift on Aurelian that was not resolved within the expected 15-minute window.",
    firstSeen: "2026-09-09 14:02",
    lastSeen: "2026-09-09 15:40",
    duration: "1h 38m",
    action: "Resolved automatically on next sync cycle.",
    runId: "run-aws-20260909-1400",
    status: "resolved",
  },
];

export const AGENT_USAGE: AgentUsage[] = [
  { name: "Marcus", inputTokens: 48200, outputTokens: 9800, totalTokens: 58000, cost: 0.09, available: true },
  { name: "Trajan", inputTokens: 62400, outputTokens: 11200, totalTokens: 73600, cost: 0.12, available: true },
  { name: "Claudius", inputTokens: 138400, outputTokens: 28600, totalTokens: 167000, cost: 0.61, available: true },
  { name: "Augustus", inputTokens: 94200, outputTokens: 18800, totalTokens: 113000, cost: 0.28, available: true },
  { name: "Aurelian", inputTokens: null, outputTokens: null, totalTokens: null, cost: null, available: false },
];

export const RECENT_OUTPUTS: RecentOutput[] = [
  { id: "out-001", workflow: "Daily Plan", title: "Daily Plan · Sep 10", createdAt: "Today 07:04", status: "approved", notionUrl: "#" },
  { id: "out-002", workflow: "Augustus Content", title: "Content Draft #88", createdAt: "Today 11:12", status: "pending", notionUrl: "#" },
  { id: "out-003", workflow: "Knowledge Digest", title: "Knowledge Digest #41", createdAt: "Yesterday 17:08", status: "approved", notionUrl: "#" },
  { id: "out-004", workflow: "Standing Research", title: "Sassanid trade routes · Proposal", createdAt: "Tue Sep 8", status: "approved", notionUrl: "#" },
  { id: "out-005", workflow: "Fleet Evaluation", title: "Fleet Evaluation #12", createdAt: "Wed Sep 2", status: "approved", notionUrl: "#" },
];

export const RELIABILITY_7D = [
  { day: "Thu", valid: 4, eligible: 5 },
  { day: "Fri", valid: 5, eligible: 5 },
  { day: "Sat", valid: 3, eligible: 4 },
  { day: "Sun", valid: 4, eligible: 4 },
  { day: "Mon", valid: 5, eligible: 6 },
  { day: "Tue", valid: 5, eligible: 6 },
  { day: "Wed", valid: 4, eligible: 5 },
];

export const MARCUS_TRAJAN_TIMELINE: RunEvent[] = [
  { time: "09:02", actor: "Marcus", event: "Requested infrastructure diagnosis from Trajan", type: "handoff" },
  { time: "09:02", actor: "Trajan", event: "Accepted handoff · Parent: run-dp-20260910-0702", type: "info" },
  { time: "09:03", actor: "Trajan", event: "Working — scanning agent config files and systemd state", type: "working" },
  { time: "09:08", actor: "Trajan", event: "Verification completed — no drift detected across 6 agents", type: "complete" },
  { time: "09:09", actor: "Trajan", event: "Replied to Marcus with diagnosis summary", type: "info" },
  { time: "09:09", actor: "Trajan", event: "Artifact attached · Sync Report #217", type: "artifact" },
  { time: "09:10", actor: "Marcus", event: "Marked handoff complete · Child run closed", type: "complete" },
];
