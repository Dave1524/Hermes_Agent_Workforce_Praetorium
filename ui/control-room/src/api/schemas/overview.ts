import { z } from "zod";
import { dataStatusSchema } from "./dataStatus";
import { runSummarySchema } from "./run";
import { usageItemSchema } from "./usage";

export const reliabilityDaySchema = z.object({
  day: z.string(),
  eligible: z.number(),
  valid: z.number(),
});

export const reliabilitySchema = z.object({
  status: z.string(),
  days: z.array(reliabilityDaySchema).default([]),
});

export const overviewSummarySchema = z.object({
  workflows: z.number().nullish(),
  healthy: z.number().nullish(),
  running: z.number().nullish(),
  failed: z.number().nullish(),
  incomplete: z.number().nullish(),
  needAttention: z.number().nullish(),
  paused: z.number().nullish(),
  unknown: z.number().nullish(),
  incompleteRuns: z.number().nullish(),
});

export const overviewResponseSchema = z.object({
  apiVersion: z.string(),
  generatedAt: z.string(),
  dataStatus: dataStatusSchema,
  summary: overviewSummarySchema,
  reliability7d: reliabilitySchema.nullish(),
  recentOutputs: z.array(runSummarySchema).default([]),
  agentUsage: z.array(usageItemSchema).default([]),
});

export type OverviewResponse = z.infer<typeof overviewResponseSchema>;
export type Reliability = z.infer<typeof reliabilitySchema>;
export type ReliabilityDay = z.infer<typeof reliabilityDaySchema>;
