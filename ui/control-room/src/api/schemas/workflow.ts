import { z } from "zod";
import { artifactSchema, runSummarySchema } from "./run";
import { costSnakeSchema, usageSnakeSchema } from "./measurement";
import { benefitSchema } from "./benefit";
import { envelope } from "./envelope";
import { dependentSchema, requirementSchema } from "./requires";

export const timerSchema = z.object({
  name: z.string().nullish(),
  activeState: z.string().nullish(),
  subState: z.string().nullish(),
  enabledState: z.string().nullish(),
  lastTriggerAt: z.string().nullish(),
  nextRunAt: z.string().nullish(),
  persistent: z.boolean().nullish(),
});

export const cadenceSchema = z.object({
  status: z.string().nullish(),
  seconds: z.number().nullish(),
  source: z.string().nullish(),
  spec: z.string().nullish(),
  persistent: z.boolean().nullish(),
  randomizedDelaySec: z.number().nullish(),
  error: z.string().nullish(),
});

export const triggerSchema = z.object({
  unit: z.string(),
  scope: z.string().nullish(),
  kind: z.string().nullish(),
  surface: z.string().nullish(),
  trigger: z.string().nullish(),
  runner: z.string().nullish(),
  route: z.string().nullish(),
  systemd: z
    .object({
      service: z.unknown().nullish(),
      timer: timerSchema.nullish(),
      status: z.string().nullish(),
      errors: z.array(z.string()).default([]),
    })
    .nullish(),
  state: z.string().nullish(),
  cadence: cadenceSchema.nullish(),
});

export const contractSchema = z
  .object({
    path: z.string().nullish(),
    trigger: z.string().nullish(),
    artifact: z.string().nullish(),
    beneficiary: z.string().nullish(),
    next_actor: z.string().nullish(),
    next_action: z.string().nullish(),
    benefit_hypothesis: z.string().nullish(),
    benefit_signal: z.string().nullish(),
    task_ids: z.array(z.string()).default([]),
  })
  .catchall(z.unknown());

export const controlActionSchema = z.object({
  id: z.string(),
  enabled: z.boolean(),
  reason: z.string().nullish(),
});

// bin/control_room_control.py ControlReceipts._seam: the page's last action is this summary of
// the newest non-preview receipt, not the receipt itself — before/after are state strings.
export const lastActionSchema = z
  .object({
    action: z.string().nullish(),
    actor: z.string().nullish(),
    reason: z.string().nullish(),
    at: z.string().nullish(),
    result: z.string().nullish(),
    refusal: z.string().nullish(),
    note: z.string().nullish(),
    before: z.string().nullish(),
    after: z.string().nullish(),
    receiptId: z.string().nullish(),
    links: z.record(z.string(), z.string().nullish()).nullish(),
  })
  .catchall(z.unknown());
export type LastAction = z.infer<typeof lastActionSchema>;

export const controlSchema = z.object({
  state: z.string().nullish(),
  source: z.string().nullish(),
  nextRunAt: z.string().nullish(),
  nextRunEstimated: z.boolean().nullish(),
  lastTriggerAt: z.string().nullish(),
  persistent: z.boolean().nullish(),
  lastAction: lastActionSchema.nullish(),
  actions: z.array(controlActionSchema).default([]),
});

export const linksSchema = z.object({
  contractLocal: z.string().nullish(),
  contractGithub: z.string().nullish(),
  devPlanTracker: z.string().nullish(),
  devPlanDoc: z.string().nullish(),
  taskIds: z.array(z.string()).default([]),
});

export const lastValidArtifactSchema = z.object({
  runId: z.string().nullish(),
  endedAt: z.string().nullish(),
  ageSeconds: z.number().nullish(),
  uri: z.string().nullish(),
  title: z.string().nullish(),
  kind: z.string().nullish(),
});

export const lineageStageSchema = z.object({
  stage: z.string(),
  value: z.union([z.string(), z.array(z.string())]).nullish(),
  source: z.string().nullish(),
});

export const workflowSchema = z.object({
  id: z.string(),
  name: z.string(),
  owners: z.array(z.string()).default([]),
  owner: z.string().nullish(),
  purpose: z.string().nullish(),
  lifecycle: z.string().nullish(),
  health: z.string().nullish(),
  surface: z.string().nullish(),
  role: z.string().nullish(),
  requires: z.array(requirementSchema).default([]),
  requiredBy: z.array(dependentSchema).default([]),
  guards: z.string().nullish(),
  manifestPaths: z.array(z.string()).default([]),
  contract: contractSchema.nullish(),
  contractStatus: z.string().nullish(),
  contractError: z.string().nullish(),
  contractExempt: z.string().nullish(),
  triggers: z.array(triggerSchema).default([]),
  lastRun: runSummarySchema.nullish(),
  latestOutput: artifactSchema.nullish(),
  usage: usageSnakeSchema.nullish(),
  cost: costSnakeSchema.nullish(),
  receiptCount: z.number().nullish(),
  cadence: cadenceSchema.nullish(),
  lastValidArtifact: lastValidArtifactSchema.nullish(),
  artifactFreshness: z.string().nullish(),
  control: controlSchema.nullish(),
  links: linksSchema.nullish(),
  benefit: benefitSchema.nullish(),
  eligibleRuns: z.number().nullish(),
  validArtifactRate: z.number().nullish(),
  incompleteRuns: z.array(runSummarySchema).default([]),
  lineage: z.array(lineageStageSchema).default([]),
});

export const workflowListResponseSchema = envelope(z.array(workflowSchema));
export const workflowDetailResponseSchema = envelope(workflowSchema);

export type Workflow = z.infer<typeof workflowSchema>;
export type Trigger = z.infer<typeof triggerSchema>;
export type Control = z.infer<typeof controlSchema>;
export type ControlAction = z.infer<typeof controlActionSchema>;
export type Contract = z.infer<typeof contractSchema>;
export type LineageStage = z.infer<typeof lineageStageSchema>;
export type Cadence = z.infer<typeof cadenceSchema>;
