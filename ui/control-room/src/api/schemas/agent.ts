import { z } from "zod";
import { envelope } from "./envelope";
import { costCamelSchema, usageCamelSchema } from "./measurement";
import { dependentSchema } from "./requires";
import { runSummarySchema } from "./run";

export const agentRuntimeSchema = z.object({
  unit: z.string().nullish(),
  scope: z.string().nullish(),
  state: z.string().nullish(),
  since: z.string().nullish(),
});

export const ownedWorkflowSchema = z.object({
  id: z.string(),
  role: z.string().nullish(),
});

export const agentSchema = z.object({
  name: z.string(),
  title: z.string().nullish(),
  harness: z.string().nullish(),
  manifest: z.string().nullish(),
  runtime: agentRuntimeSchema.nullish(),
  health: z.string().nullish(),
  lastTurn: runSummarySchema.nullish(),
  turns7d: z.number().nullish(),
  usage7d: usageCamelSchema.nullish(),
  cost7d: costCamelSchema.nullish(),
  ownedWorkflows: z.array(ownedWorkflowSchema).default([]),
  requiredBy: z.array(dependentSchema).default([]),
});

export const agentListResponseSchema = envelope(z.array(agentSchema));
export const agentDetailResponseSchema = envelope(agentSchema);

export type Agent = z.infer<typeof agentSchema>;
export type AgentRuntime = z.infer<typeof agentRuntimeSchema>;
