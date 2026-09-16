import type { Contract, Trigger, Workflow } from "@/api/schemas/workflow";
import { type Benefit, toBenefit } from "./benefit";
import { type Run, toRun } from "./run";
import { type WorkflowRow, toWorkflowRow } from "./workflowRow";

export interface TriggerView {
  unit: string;
  kind: string | null;
  scope: string | null;
  timerState: string | null;
  enabledState: string | null;
  lastTriggerAt: string | null;
  nextRunAt: string | null;
  spec: string | null;
  cadenceSeconds: number | null;
  persistent: boolean | null;
  errors: string[];
}

export interface LineageView {
  stage: string;
  value: string[];
  source: string | null;
}

export interface ActionView {
  id: string;
  enabled: boolean;
  reason: string | null;
}

export interface LinksView {
  contractLocal: string | null;
  contractGithub: string | null;
  devPlanTracker: string | null;
  devPlanDoc: string | null;
  taskIds: string[];
}

export interface WorkflowDetail {
  row: WorkflowRow;
  purpose: string | null;
  owners: string[];
  manifestPaths: string[];
  contract: Contract | null;
  contractStatus: string | null;
  contractError: string | null;
  triggers: TriggerView[];
  lineage: LineageView[];
  benefit: Benefit | null;
  links: LinksView | null;
  actions: ActionView[];
  lastRun: Run | null;
  incompleteRuns: Run[];
  lastValidArtifactAt: string | null;
  controlSource: string | null;
  lastTriggerAt: string | null;
}

const toTrigger = (t: Trigger): TriggerView => ({
  unit: t.unit,
  kind: t.kind ?? null,
  scope: t.scope ?? null,
  timerState: t.systemd?.timer?.activeState ?? t.state ?? null,
  enabledState: t.systemd?.timer?.enabledState ?? null,
  lastTriggerAt: t.systemd?.timer?.lastTriggerAt ?? null,
  nextRunAt: t.systemd?.timer?.nextRunAt ?? null,
  spec: t.cadence?.spec ?? t.trigger ?? null,
  cadenceSeconds: t.cadence?.seconds ?? null,
  persistent: t.cadence?.persistent ?? t.systemd?.timer?.persistent ?? null,
  errors: t.systemd?.errors ?? [],
});

const lineageValue = (v: string | string[] | null | undefined): string[] => (Array.isArray(v) ? v : v ? [v] : []);

export const toWorkflowDetail = (w: Workflow): WorkflowDetail => ({
  row: toWorkflowRow(w),
  purpose: w.purpose ?? null,
  owners: w.owners,
  manifestPaths: w.manifestPaths,
  contract: w.contract ?? null,
  contractStatus: w.contractStatus ?? null,
  contractError: w.contractError ?? null,
  triggers: w.triggers.map(toTrigger),
  lineage: w.lineage.map((s) => ({ stage: s.stage, value: lineageValue(s.value), source: s.source ?? null })),
  benefit: toBenefit(w.benefit),
  links: w.links
    ? {
        contractLocal: w.links.contractLocal ?? null,
        contractGithub: w.links.contractGithub ?? null,
        devPlanTracker: w.links.devPlanTracker ?? null,
        devPlanDoc: w.links.devPlanDoc ?? null,
        taskIds: w.links.taskIds,
      }
    : null,
  actions: (w.control?.actions ?? []).map((a) => ({ id: a.id, enabled: a.enabled, reason: a.reason ?? null })),
  lastRun: w.lastRun ? toRun(w.lastRun) : null,
  incompleteRuns: w.incompleteRuns.map(toRun),
  lastValidArtifactAt: w.lastValidArtifact?.endedAt ?? null,
  controlSource: w.control?.source ?? null,
  lastTriggerAt: w.control?.lastTriggerAt ?? null,
});
