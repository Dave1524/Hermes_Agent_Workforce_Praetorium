import { z } from "zod";

export const healthResponseSchema = z.object({
  status: z.string(),
  apiVersion: z.string().nullish(),
  generatedAt: z.string().nullish(),
  sources: z.record(z.string(), z.string()).default({}),
  errors: z.record(z.string(), z.unknown()).default({}),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;
