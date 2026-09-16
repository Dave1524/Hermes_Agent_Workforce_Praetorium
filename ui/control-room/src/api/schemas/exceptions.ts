import { z } from "zod";
import { envelope } from "./envelope";

export const exceptionRowSchema = z.object({
  kind: z.string(),
  workflowId: z.string().nullish(),
  owner: z.string().nullish(),
  issue: z.string().nullish(),
  failedAssertions: z.array(z.string()).default([]),
  requiredAction: z.string().nullish(),
  evidence: z
    .object({ runId: z.string().nullish(), artifactUri: z.string().nullish() })
    .nullish(),
  paused: z.boolean().nullish(),
  since: z.string().nullish(),
  alsoFailed: z.boolean().nullish(),
});

export const dataQualityRowSchema = z
  .object({
    id: z.string(),
    severity: z.string().nullish(),
    status: z.string().nullish(),
    workflowId: z.string().nullish(),
    agent: z.string().nullish(),
    issue: z.string().nullish(),
    failedAssertion: z.string().nullish(),
    requiredAction: z.string().nullish(),
    runId: z.string().nullish(),
    evidence: z.array(z.string()).default([]),
  })
  .catchall(z.unknown());

export const exceptionsResponseSchema = envelope(z.array(exceptionRowSchema)).extend({
  dataQuality: z.array(dataQualityRowSchema).default([]),
});

export type ExceptionRow = z.infer<typeof exceptionRowSchema>;
export type DataQualityRow = z.infer<typeof dataQualityRowSchema>;
export type ExceptionsResponse = z.infer<typeof exceptionsResponseSchema>;
