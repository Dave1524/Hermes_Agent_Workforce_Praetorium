import { z } from "zod";
import { envelope } from "./envelope";

export const incidentSchema = z.object({
  id: z.string(),
  status: z.string(),
  class: z.string().nullish(),
  key: z.string().nullish(),
  severity: z.string().nullish(),
  workflowId: z.string().nullish(),
  agent: z.string().nullish(),
  issue: z.string().nullish(),
  failedAssertion: z.string().nullish(),
  requiredAction: z.string().nullish(),
  runId: z.string().nullish(),
  evidence: z.array(z.string()).default([]),
  firstSeen: z.string().nullish(),
  lastSeen: z.string().nullish(),
  resolvedAt: z.string().nullish(),
  notifiedAt: z.string().nullish(),
  observations: z.number().nullish(),
});

export const incidentsResponseSchema = envelope(z.array(incidentSchema));

export type Incident = z.infer<typeof incidentSchema>;
