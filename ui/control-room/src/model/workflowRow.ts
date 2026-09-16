import type { Workflow } from "@/api/schemas/workflow";
import { type ControlState, toControlState } from "./controlState";
import { type Health, toHealth } from "./health";
import { type Cost, type Measurement, type Usage, costFromSnake, usageFromSnake } from "./measurement";
import { type Outcome, toOutcome } from "./outcome";
import { type DependentView, type RequirementView, toDependent, toRequirement } from "./requires";
import { type Role, toRole } from "./role";

export interface WorkflowRow {
  id: string;
  name: string;
  owner: string | null;
  health: Health;
  role: Role;
  surface: string | null;
  requires: RequirementView[];
  requiredBy: DependentView[];
  guards: string | null;
  controlState: ControlState;
  lifecycle: string | null;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastOutcome: Outcome;
  nextRunAt: string | null;
  nextRunEstimated: boolean;
  cadenceSeconds: number | null;
  cadenceSpec: string | null;
  usage: Measurement<Usage>;
  cost: Measurement<Cost>;
  artifactFreshness: string | null;
  receiptCount: number | null;
  validArtifactRate: number | null;
}

export const toWorkflowRow = (w: Workflow): WorkflowRow => ({
  id: w.id,
  name: w.name,
  owner: w.owner ?? w.owners[0] ?? null,
  health: toHealth(w.health),
  role: toRole(w.role),
  surface: w.surface ?? null,
  requires: w.requires.map(toRequirement),
  requiredBy: w.requiredBy.map(toDependent),
  guards: w.guards ?? null,
  controlState: toControlState(w.control?.state),
  lifecycle: w.lifecycle ?? null,
  lastRunAt: w.lastRun?.endedAt ?? w.lastRun?.startedAt ?? null,
  lastRunId: w.lastRun?.id ?? null,
  lastOutcome: toOutcome(w.lastRun?.outcome),
  nextRunAt: w.control?.nextRunAt ?? null,
  nextRunEstimated: w.control?.nextRunEstimated ?? false,
  cadenceSeconds: w.cadence?.seconds ?? null,
  cadenceSpec: w.cadence?.spec ?? null,
  usage: usageFromSnake(w.usage),
  cost: costFromSnake(w.cost),
  artifactFreshness: w.artifactFreshness ?? null,
  receiptCount: w.receiptCount ?? null,
  validArtifactRate: w.validArtifactRate ?? null,
});
