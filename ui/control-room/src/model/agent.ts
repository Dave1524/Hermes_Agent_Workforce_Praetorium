import type { Agent } from "@/api/schemas/agent";
import type { LastAction } from "@/api/schemas/workflow";
import { type Health, toHealth } from "./health";
import { type Cost, type Measurement, type Usage, costFromCamel, usageFromCamel } from "./measurement";
import { type DependentView, toDependent } from "./requires";
import { type Role, toRole } from "./role";
import { type Run, toRun } from "./run";
import { type ActionView, toActions } from "./workflowDetail";

export type RuntimeStatus = "up" | "down" | "unknown";

export interface RuntimeView {
  unit: string | null;
  scope: string | null;
  state: string;
  status: RuntimeStatus;
  since: string | null;
  unitFileState: string | null;
}

export interface OwnedWorkflow {
  id: string;
  role: Role;
}

export interface AgentView {
  name: string;
  title: string | null;
  harness: string | null;
  manifest: string | null;
  runtime: RuntimeView;
  actions: ActionView[];
  lastAction: LastAction | null;
  health: Health;
  lastTurn: Run | null;
  turns7d: number | null;
  usage7d: Measurement<Usage>;
  cost7d: Measurement<Cost>;
  ownedWorkflows: OwnedWorkflow[];
  requiredBy: DependentView[];
}

// systemd ActiveState, the same set bin/workflow_requires.py counts as satisfied.
const UP_STATES = ["active", "activating", "reloading"];

export const toRuntimeStatus = (state: string | null | undefined): RuntimeStatus => {
  if (!state || state === "unknown") return "unknown";
  return UP_STATES.includes(state) ? "up" : "down";
};

export const toAgent = (a: Agent): AgentView => ({
  name: a.name,
  title: a.title ?? null,
  harness: a.harness ?? null,
  manifest: a.manifest ?? null,
  runtime: {
    unit: a.runtime?.unit ?? null,
    scope: a.runtime?.scope ?? null,
    state: a.runtime?.state ?? "unknown",
    status: toRuntimeStatus(a.runtime?.state),
    since: a.runtime?.since ?? null,
    unitFileState: a.runtime?.unitFileState ?? null,
  },
  actions: toActions(a.control),
  lastAction: a.control?.lastAction ?? null,
  health: toHealth(a.health),
  lastTurn: a.lastTurn ? toRun(a.lastTurn) : null,
  turns7d: a.turns7d ?? null,
  usage7d: usageFromCamel(a.usage7d),
  cost7d: costFromCamel(a.cost7d),
  ownedWorkflows: a.ownedWorkflows.map((w) => ({ id: w.id, role: toRole(w.role) })),
  requiredBy: a.requiredBy.map(toDependent),
});
