import { z } from "zod";
import { costSnakeSchema, usageSnakeSchema } from "./measurement";
import { envelope } from "./envelope";

export const artifactSchema = z.object({
  uri: z.string().nullish(),
  title: z.string().nullish(),
  kind: z.string().nullish(),
});

export const assertionSchema = z
  .object({
    id: z.string(),
    status: z.string(),
    message: z.string().nullish(),
    output: z.string().nullish(),
  })
  .catchall(z.unknown());

export const nextActionSchema = z
  .object({
    actor: z.string().nullish(),
    action: z.string().nullish(),
    due_at: z.string().nullish(),
  })
  .catchall(z.unknown());

export const closedSchema = z.object({
  at: z.string(),
  by: z.string(),
  reason: z.string(),
});

export const sweptSchema = z.object({
  at: z.string(),
  sweep_run_id: z.string(),
});

export const runSummarySchema = z.object({
  id: z.string().nullish(),
  workflowId: z.string().nullish(),
  unit: z.string().nullish(),
  agent: z.string().nullish(),
  model: z.string().nullish(),
  startedAt: z.string().nullish(),
  endedAt: z.string().nullish(),
  outcome: z.string().nullish(),
  reason: z.string().nullish(),
  artifact: artifactSchema.nullish(),
  stateChange: z.unknown().nullish(),
  assertions: z.array(assertionSchema).default([]),
  usage: usageSnakeSchema.nullish(),
  cost: costSnakeSchema.nullish(),
  nextAction: nextActionSchema.nullish(),
  parentRunId: z.string().nullish(),
  handoff: z.unknown().nullish(),
  receiptPath: z.string().nullish(),
  closed: closedSchema.nullish(),
  swept: sweptSchema.nullish(),
});

export const runDetailResponseSchema = envelope(runSummarySchema);
export const runListResponseSchema = envelope(z.array(runSummarySchema));

export type RunSummary = z.infer<typeof runSummarySchema>;
export type Artifact = z.infer<typeof artifactSchema>;
export type Assertion = z.infer<typeof assertionSchema>;
export type Closed = z.infer<typeof closedSchema>;
export type Swept = z.infer<typeof sweptSchema>;
