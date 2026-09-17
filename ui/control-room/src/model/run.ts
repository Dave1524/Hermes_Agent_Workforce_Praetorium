import type { RunSummary } from "@/api/schemas/run";
import { type Cost, type Measurement, type Usage, costFromSnake, usageFromSnake } from "./measurement";
import { type Outcome, toOutcome } from "./outcome";
import { durationSeconds } from "./time";

export interface RunArtifact {
  uri: string | null;
  title: string | null;
  kind: string | null;
}

export interface RunAssertion {
  id: string;
  status: string;
  message: string | null;
}

export interface RunClosure {
  at: string;
  by: string;
  reason: string;
}

export interface RunSweep {
  at: string;
  sweepRunId: string;
}

export interface NextAction {
  actor: string | null;
  action: string | null;
  dueAt: string | null;
}

export interface Run {
  id: string;
  workflowId: string | null;
  unit: string | null;
  agent: string | null;
  model: string | null;
  startedAt: string | null;
  endedAt: string | null;
  durationSeconds: number | null;
  outcome: Outcome;
  reason: string | null;
  artifact: RunArtifact | null;
  assertions: RunAssertion[];
  usage: Measurement<Usage>;
  cost: Measurement<Cost>;
  nextAction: NextAction | null;
  parentRunId: string | null;
  handoff: unknown;
  receiptPath: string | null;
  closed: RunClosure | null;
  swept: RunSweep | null;
}

export const toRun = (r: RunSummary): Run => ({
  id: r.id ?? "",
  workflowId: r.workflowId ?? null,
  unit: r.unit ?? null,
  agent: r.agent ?? null,
  model: r.model ?? null,
  startedAt: r.startedAt ?? null,
  endedAt: r.endedAt ?? null,
  durationSeconds: durationSeconds(r.startedAt, r.endedAt),
  outcome: toOutcome(r.outcome),
  reason: r.reason ?? null,
  artifact: r.artifact ? { uri: r.artifact.uri ?? null, title: r.artifact.title ?? null, kind: r.artifact.kind ?? null } : null,
  assertions: r.assertions.map((a) => ({ id: a.id, status: a.status, message: a.message ?? a.output ?? null })),
  usage: usageFromSnake(r.usage),
  cost: costFromSnake(r.cost),
  nextAction: r.nextAction ? { actor: r.nextAction.actor ?? null, action: r.nextAction.action ?? null, dueAt: r.nextAction.due_at ?? null } : null,
  parentRunId: r.parentRunId ?? null,
  handoff: r.handoff ?? null,
  receiptPath: r.receiptPath ?? null,
  closed: r.closed ? { at: r.closed.at, by: r.closed.by, reason: r.closed.reason } : null,
  swept: r.swept ? { at: r.swept.at, sweepRunId: r.swept.sweep_run_id } : null,
});
