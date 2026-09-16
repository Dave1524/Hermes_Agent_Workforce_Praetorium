import type { Dependent, Requirement } from "@/api/schemas/requires";

export interface RequirementView {
  unit: string;
  scope: string | null;
  workflow: string | null;
  agent: string | null;
  state: string;
  satisfied: boolean | null;
}

export interface DependentView {
  workflow: string;
  enabled: boolean | null;
}

export type RequiresStatus = "satisfied" | "down" | "unknown";

const RUNTIME_PREFIX = "buzz-agent@";

export const agentOfUnit = (unit: string): string | null => {
  if (!unit.startsWith(RUNTIME_PREFIX)) return null;
  return unit.slice(RUNTIME_PREFIX.length).replace(/\.service$/, "") || null;
};

export const toRequirement = (r: Requirement): RequirementView => ({
  unit: r.unit,
  scope: r.scope ?? null,
  workflow: r.workflow ?? null,
  agent: agentOfUnit(r.unit),
  state: r.state ?? "unknown",
  satisfied: r.satisfied ?? null,
});

export const toDependent = (d: Dependent): DependentView => ({ workflow: d.workflow, enabled: d.enabled ?? null });

export const firstUnsatisfied = (rows: RequirementView[]): RequirementView | null => rows.find((r) => r.satisfied === false) ?? null;

export const requiresStatus = (rows: RequirementView[]): RequiresStatus => {
  if (firstUnsatisfied(rows)) return "down";
  return rows.some((r) => r.satisfied === null) ? "unknown" : "satisfied";
};

export const enabledDependents = (rows: DependentView[]): DependentView[] => rows.filter((d) => d.enabled === true);
