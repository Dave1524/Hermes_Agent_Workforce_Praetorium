import { z } from "zod";
import { envelope } from "./envelope";

export const consumptionSchema = z.object({
  status: z.string(),
  opened: z.number().nullish(),
  approved: z.number().nullish(),
  sent: z.number().nullish(),
  marked_useful: z.number().nullish(),
  artifactRuns: z.number().nullish(),
});

export const benefitSchema = z.object({
  workflowId: z.string().nullish(),
  decision: z.string().nullish(),
  baseline: z.unknown().nullish(),
  eligibleRuns: z.number().nullish(),
  validArtifactRate: z.number().nullish(),
  latencySeconds: z.number().nullish(),
  consumption: consumptionSchema.nullish(),
  manualMinutesAvoided: z.number().nullish(),
  decidedAt: z.string().nullish(),
  decidedBy: z.string().nullish(),
  evidence: z.unknown().nullish(),
});

export const benefitResponseSchema = envelope(z.array(benefitSchema));

export type Benefit = z.infer<typeof benefitSchema>;
export type Consumption = z.infer<typeof consumptionSchema>;
