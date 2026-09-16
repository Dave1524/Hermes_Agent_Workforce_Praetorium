import type { Workflow } from "./schemas/workflow";
import type { RunSummary } from "./schemas/run";
import type { ExceptionRow } from "./schemas/exceptions";
import type { Incident } from "./schemas/incidents";
import type { UsageItem } from "./schemas/usage";
import type { OverviewResponse } from "./schemas/overview";
import type { Agent } from "./schemas/agent";

// Shapes mirror tests/fixtures/control-room receipts at NOW = 2026-09-14T08:00:00Z.
export const FIXTURE_NOW = new Date("2026-09-14T08:00:00Z");

export const measuredRun: RunSummary = {
  id: "run-0914",
  workflowId: "agent-inbox-sync",
  unit: "agent-inbox-sync.service",
  agent: "marcus",
  model: "claude-opus-5",
  startedAt: "2026-09-14T07:00:00Z",
  endedAt: "2026-09-14T07:02:30Z",
  outcome: "artifact",
  reason: null,
  artifact: { uri: "notion://inbox/2026-09-14", title: "Inbox sync 2026-09-14", kind: "notion" },
  assertions: [{ id: "row-written", status: "pass", message: null }],
  usage: { status: "measured", input_tokens: 1200, output_tokens: 300, cache_tokens: 0, total_tokens: 1500 },
  cost: { status: "measured", amount: 0.42, currency: "USD", source: "receipt", confidence: "measured" },
  nextAction: { actor: "dave", action: "review", due_at: "2026-09-15T08:00:00Z" },
  parentRunId: null,
  receiptPath: "var/workflow-receipts/agent-inbox-sync/run-0914.json",
};

export const failedRun: RunSummary = {
  ...measuredRun,
  id: "run-0913",
  workflowId: "raw-ingest",
  agent: "claudius",
  startedAt: "2026-09-13T03:00:00Z",
  endedAt: "2026-09-13T03:04:00Z",
  outcome: "failed",
  reason: "assertion failed: proposal-or-decline",
  artifact: null,
  assertions: [{ id: "proposal-or-decline", status: "fail", message: "neither a proposal nor DECLINE:" }],
  usage: { status: "unavailable", input_tokens: null, output_tokens: null, cache_tokens: null, total_tokens: null },
  cost: { status: "unavailable", amount: null, currency: null, source: null, confidence: null },
  nextAction: null,
};

export const skippedRun: RunSummary = {
  ...measuredRun,
  id: "run-0914-skip",
  workflowId: "memory-consolidation",
  outcome: "skipped",
  reason: "nothing to consolidate",
  artifact: null,
  assertions: [],
};

export const activeWorkflow: Workflow = {
  id: "agent-inbox-sync",
  name: "Agent inbox sync",
  owners: ["marcus"],
  owner: "marcus",
  purpose: "Mirror the agent inbox into Notion",
  lifecycle: "active",
  health: "healthy",
  surface: "scheduled",
  role: "agent-workflow",
  requires: [
    { unit: "buzz-agent@marcus", scope: "user", workflow: "buzz-agent@marcus", state: "active", satisfied: true },
    { unit: "buzz-notion-broker", scope: "user", workflow: null, state: "active", satisfied: true },
  ],
  requiredBy: [],
  guards: null,
  manifestPaths: ["design/workflows/agent-inbox-sync.toml"],
  contract: { path: "design/contracts/agent-inbox-sync.toml", trigger: "timer", artifact: "notion row", beneficiary: "dave", next_actor: "dave", next_action: "review", benefit_hypothesis: "less manual triage", benefit_signal: "opened", task_ids: ["T5.1"] },
  contractStatus: "ok",
  contractError: null,
  triggers: [
    {
      unit: "agent-inbox-sync.timer",
      scope: "system",
      kind: "timer",
      surface: "systemd",
      trigger: "OnCalendar=*:0/15",
      systemd: {
        service: null,
        timer: { name: "agent-inbox-sync.timer", activeState: "active", subState: "waiting", enabledState: "enabled", lastTriggerAt: "2026-09-14T07:00:00Z", nextRunAt: "2026-09-14T07:15:00Z", persistent: true },
        status: "available",
        errors: [],
      },
      state: "active",
      cadence: { status: "measured", seconds: 900, source: "unit", spec: "*:0/15", persistent: true, randomizedDelaySec: 0, error: null },
    },
  ],
  lastRun: measuredRun,
  latestOutput: measuredRun.artifact,
  usage: measuredRun.usage,
  cost: measuredRun.cost,
  receiptCount: 12,
  cadence: { status: "measured", seconds: 900, source: "unit", spec: "*:0/15", persistent: true, randomizedDelaySec: 0, error: null },
  lastValidArtifact: { runId: "run-0914", endedAt: "2026-09-14T07:02:30Z", ageSeconds: 3450, uri: "notion://inbox/2026-09-14", title: "Inbox sync 2026-09-14", kind: "notion" },
  artifactFreshness: "fresh",
  control: {
    state: "active",
    source: "systemd",
    nextRunAt: "2026-09-14T07:15:00Z",
    nextRunEstimated: false,
    lastTriggerAt: "2026-09-14T07:00:00Z",
    persistent: true,
    lastAction: null,
    actions: [
      { id: "pause", enabled: true, reason: null },
      { id: "resume", enabled: false, reason: "already active" },
      { id: "run_now", enabled: true, reason: null },
      { id: "retry", enabled: false, reason: "last run succeeded" },
      { id: "stop", enabled: false, reason: "not running" },
    ],
  },
  links: { contractLocal: "design/contracts/agent-inbox-sync.toml", contractGithub: "https://github.com/x/y/blob/main/design/contracts/agent-inbox-sync.toml", devPlanTracker: null, devPlanDoc: null, taskIds: ["T5.1"] },
  benefit: { workflowId: "agent-inbox-sync", decision: "Keep", baseline: null, eligibleRuns: 12, validArtifactRate: 0.92, latencySeconds: 150, consumption: { status: "measured", opened: 10, approved: 4, sent: 0, marked_useful: 3, artifactRuns: 11 }, manualMinutesAvoided: 120, decidedAt: "2026-09-10T00:00:00Z", decidedBy: "dave", evidence: null },
  eligibleRuns: 12,
  validArtifactRate: 0.92,
  incompleteRuns: [],
  lineage: [
    { stage: "trigger", value: "agent-inbox-sync.timer", source: "unit" },
    { stage: "runner", value: "bin/agent_inbox_pipeline.sh", source: "manifest" },
    { stage: "artifact", value: "notion row", source: "contract" },
  ],
};

export const pausedWorkflow: Workflow = {
  ...activeWorkflow,
  id: "raw-ingest",
  name: "Raw ingest",
  owners: ["claudius"],
  owner: "claudius",
  health: "failed",
  requires: [{ unit: "ollama.service", scope: "system", workflow: null, state: "inactive", satisfied: false }],
  lastRun: failedRun,
  latestOutput: null,
  usage: failedRun.usage,
  cost: failedRun.cost,
  artifactFreshness: "stale",
  control: {
    ...activeWorkflow.control!,
    state: "paused",
    nextRunAt: "2026-09-16T03:00:00Z",
    nextRunEstimated: true,
    actions: [
      { id: "pause", enabled: false, reason: "already paused" },
      { id: "resume", enabled: true, reason: null },
      { id: "run_now", enabled: true, reason: null },
      { id: "retry", enabled: true, reason: null },
      { id: "stop", enabled: false, reason: "not running" },
    ],
  },
  benefit: { ...activeWorkflow.benefit!, workflowId: "raw-ingest", decision: "Improve" },
};

export const unavailableWorkflow: Workflow = {
  id: "weekly-pre-assembly",
  name: "Weekly pre-assembly",
  owners: [],
  owner: null,
  purpose: null,
  lifecycle: "active",
  health: "unknown",
  surface: "platform",
  role: "system-workflow",
  requires: [{ unit: "qmd-mcp", scope: "system", workflow: null, state: "unknown", satisfied: null }],
  requiredBy: [],
  guards: "Without it the weekly pre-read is never assembled.",
  manifestPaths: [],
  contract: null,
  contractStatus: "missing",
  contractError: "no contract",
  triggers: [],
  lastRun: null,
  latestOutput: null,
  usage: { status: "unavailable", input_tokens: null, output_tokens: null, cache_tokens: null, total_tokens: null },
  cost: { status: "unavailable", amount: null, currency: null, source: null, confidence: null },
  receiptCount: 0,
  cadence: { status: "unavailable", seconds: null, source: null, spec: null, persistent: null, randomizedDelaySec: null, error: "no timer" },
  lastValidArtifact: null,
  artifactFreshness: null,
  control: { state: "unknown", source: null, nextRunAt: null, nextRunEstimated: null, lastTriggerAt: null, persistent: null, lastAction: null, actions: [] },
  links: null,
  benefit: null,
  eligibleRuns: null,
  validArtifactRate: null,
  incompleteRuns: [],
  lineage: [],
};

export const runtimeWorkflow: Workflow = {
  ...unavailableWorkflow,
  id: "buzz-agent@marcus",
  name: "buzz-agent@marcus",
  owners: ["marcus"],
  owner: "marcus",
  purpose: "Marcus's live Buzz session",
  health: "healthy",
  surface: "interactive",
  role: "agent-runtime",
  requires: [],
  requiredBy: [{ workflow: "agent-inbox-sync", enabled: true }],
  guards: null,
  control: { ...unavailableWorkflow.control!, state: "active" },
};

export const dependencyDownException: ExceptionRow = {
  kind: "dependency-down",
  workflowId: "raw-ingest",
  owner: "claudius",
  issue: "requires ollama.service (system): inactive",
  failedAssertions: [],
  requiredAction: "Start the required unit or resume its workflow; until then every run is refused at pre-flight.",
  evidence: { runId: null, artifactUri: null },
  paused: false,
  since: null,
  alsoFailed: null,
};

export const failedException: ExceptionRow = {
  kind: "failed",
  workflowId: "raw-ingest",
  owner: "claudius",
  issue: "assertion failed: proposal-or-decline",
  failedAssertions: ["proposal-or-decline"],
  requiredAction: "Retry after fixing the profile",
  evidence: { runId: "run-0913", artifactUri: null },
  paused: true,
  since: "2026-09-13T03:04:00Z",
  alsoFailed: null,
};

export const openIncident: Incident = {
  id: "inc-1",
  status: "open",
  class: "failed-run",
  key: "raw-ingest:proposal-or-decline",
  severity: "high",
  workflowId: "raw-ingest",
  agent: "claudius",
  issue: "assertion failed: proposal-or-decline",
  failedAssertion: "proposal-or-decline",
  requiredAction: "Retry after fixing the profile",
  runId: "run-0913",
  evidence: ["var/workflow-receipts/raw-ingest/run-0913.json"],
  firstSeen: "2026-09-13T03:04:00Z",
  lastSeen: "2026-09-14T07:00:00Z",
  resolvedAt: null,
  notifiedAt: "2026-09-13T03:05:00Z",
  observations: 3,
};

export const measuredUsage: UsageItem = {
  agent: "marcus",
  runCount: 4,
  usage: { status: "measured", inputTokens: 4800, outputTokens: 1200, cacheTokens: 0, totalTokens: 6000 },
  cost: { status: "measured", amount: 1.68, currency: "USD" },
};

export const unavailableUsage: UsageItem = {
  agent: "trajan",
  runCount: 1,
  usage: { status: "unavailable", inputTokens: null, outputTokens: null, cacheTokens: null, totalTokens: null },
  cost: { status: "unavailable", amount: null, currency: null },
};

export const overview: OverviewResponse = {
  apiVersion: "1",
  generatedAt: "2026-09-14T08:00:00Z",
  dataStatus: { manifests: "available", receipts: "available", systemd: "available", errors: {} },
  summary: { workflows: 31, healthy: 22, running: 1, failed: 1, incomplete: 0, needAttention: 4, paused: 30, unknown: 2, incompleteRuns: 0, agents: { total: 5, up: 4, down: 0, unknown: 1 } },
  reliability7d: {
    status: "measured",
    days: [
      { day: "2026-09-08", eligible: 1, valid: 0 },
      { day: "2026-09-09", eligible: 0, valid: 0 },
      { day: "2026-09-10", eligible: 1, valid: 1 },
      { day: "2026-09-11", eligible: 1, valid: 1 },
      { day: "2026-09-12", eligible: 2, valid: 1 },
      { day: "2026-09-13", eligible: 2, valid: 1 },
      { day: "2026-09-14", eligible: 1, valid: 1 },
    ],
  },
  recentOutputs: [measuredRun],
  agentUsage: [measuredUsage, unavailableUsage],
};

export const interactionTurn: RunSummary = {
  ...measuredRun,
  id: "turn-0914",
  workflowId: "buzz-agent@marcus",
  unit: "buzz-agent@marcus.service",
  startedAt: "2026-09-14T07:30:00Z",
  endedAt: "2026-09-14T07:31:10Z",
  artifact: { uri: null, title: "reply in #ops", kind: "buzz-message" },
  assertions: [],
  nextAction: null,
  receiptPath: "var/workflow-receipts/buzz-agent@marcus/turn-0914.json",
};

export const agentUp: Agent = {
  name: "marcus",
  title: "Chief of staff",
  harness: "claude-agent-acp",
  manifest: "design/agents/marcus.toml",
  runtime: { unit: "buzz-agent@marcus", scope: "user", state: "active", since: "2026-09-13T21:04:35Z" },
  health: "healthy",
  lastTurn: interactionTurn,
  turns7d: 3,
  usage7d: measuredUsage.usage,
  cost7d: measuredUsage.cost,
  ownedWorkflows: [{ id: "agent-inbox-sync", role: "agent-workflow" }],
  requiredBy: [{ workflow: "agent-inbox-sync", enabled: true }],
};

export const agentDown: Agent = {
  name: "aurelian",
  title: "Cold verification",
  harness: "claude-agent-acp",
  manifest: "design/agents/aurelian.toml",
  runtime: { unit: "buzz-agent@aurelian", scope: "user", state: "unknown", since: null },
  health: "unknown",
  lastTurn: null,
  turns7d: 0,
  usage7d: unavailableUsage.usage,
  cost7d: unavailableUsage.cost,
  ownedWorkflows: [],
  requiredBy: [],
};
