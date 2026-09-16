import { z } from "zod";
import { controlSchema } from "./workflow";

// POST /api/v1/control/proposals — the T5.3b seam (bin/control_room_proposals.py, bin/workflow_pr.py).
export const proposalKindSchema = z.enum(["schedule", "retire"]);
export type ProposalKind = z.infer<typeof proposalKindSchema>;

export const scheduleProposedSchema = z.object({
  on_calendar: z.array(z.string()),
  randomized_delay_sec: z.string().nullable(),
  persistent: z.boolean().nullable(),
  trigger: z.string().nullable(),
  acknowledge_pinned_tests: z.boolean().optional(),
});

export const retireProposedSchema = z.object({
  artifact_retention: z.object({
    receipts: z.string(),
    notion: z.string(),
    inbox: z.string(),
    note: z.string(),
  }),
  acknowledge_pinned_tests: z.boolean(),
});

export const proposalRequestSchema = z.object({
  workflow_id: z.string(),
  kind: proposalKindSchema,
  stage: z.enum(["preview", "submit", "list"]),
  reason: z.string().optional(),
  preview_token: z.string().nullable().optional(),
  proposed: z.union([scheduleProposedSchema, retireProposedSchema]).optional(),
});
export type ProposalRequest = z.infer<typeof proposalRequestSchema>;
export type ScheduleProposed = z.infer<typeof scheduleProposedSchema>;
export type RetireProposed = z.infer<typeof retireProposedSchema>;

export const proposalCheckSchema = z
  .object({
    id: z.string(),
    class: z.string().nullish(),
    status: z.string(),
    output: z.string().nullish(),
  })
  .catchall(z.unknown());

export const residueItemSchema = z
  .object({
    class: z.string().nullish(),
    what: z.string().nullish(),
    path: z.string().nullish(),
    tree: z.string().nullish(),
    has_check: z.unknown().nullish(),
    clears: z.string().nullish(),
    how: z.string().nullish(),
  })
  .catchall(z.unknown());

export const residueReportSchema = z
  .object({ verdict: z.string().nullish(), items: z.array(residueItemSchema).default([]) })
  .catchall(z.unknown());

export const proposalPreviewSchema = z
  .object({
    stage: z.literal("preview"),
    proposal_id: z.string(),
    preview_token: z.string(),
    expires_at: z.string().nullish(),
    base: z.string().nullish(),
    branch: z.string().nullish(),
    summary: z.string().nullish(),
    description: z.record(z.string(), z.unknown()).nullish(),
    files: z.array(z.string()).default([]),
    diff: z.string().nullish(),
    diff_sha256: z.string().nullish(),
    checks: z.array(proposalCheckSchema).default([]),
    residue: z.object({ source: residueReportSchema.nullish(), live: residueReportSchema.nullish() }).nullish(),
    retention: z.unknown().nullish(),
    submit_allowed: z.boolean(),
    submit_blockers: z.array(z.string()).default([]),
    control: controlSchema.nullish(),
    record: z.unknown().nullish(),
  })
  .catchall(z.unknown());

export const proposalSubmittedSchema = z
  .object({
    stage: z.literal("submitted"),
    proposal_id: z.string(),
    pr: z.object({ url: z.string(), number: z.number().nullish(), branch: z.string().nullish(), draft: z.boolean().nullish() }),
    diff_sha256: z.string().nullish(),
    control: controlSchema.nullish(),
  })
  .catchall(z.unknown());

export const proposalRecordSchema = z
  .object({
    proposal_id: z.string(),
    kind: z.string().nullish(),
    stage: z.string().nullish(),
    reason: z.string().nullish(),
    completed_at: z.string().nullish(),
    pr: z.object({ url: z.string().nullish(), number: z.number().nullish() }).nullish(),
  })
  .catchall(z.unknown());

export const proposalListSchema = z.object({
  stage: z.literal("list"),
  items: z.array(proposalRecordSchema).default([]),
});

export const proposalRefusalSchema = z.object({
  error: z.union([
    z.object({ code: z.string(), message: z.string().nullish(), choices: z.array(z.string()).nullish(), diff: z.string().nullish() }),
    z.string(),
  ]),
  record: z.unknown().nullish(),
  control: controlSchema.nullish(),
});

export const proposalResponseSchema = z.union([
  proposalPreviewSchema,
  proposalSubmittedSchema,
  proposalListSchema,
  proposalRefusalSchema,
]);

export type ProposalPreview = z.infer<typeof proposalPreviewSchema>;
export type ProposalSubmitted = z.infer<typeof proposalSubmittedSchema>;
export type ProposalList = z.infer<typeof proposalListSchema>;
export type ProposalRefusal = z.infer<typeof proposalRefusalSchema>;
export type ProposalResponse = z.infer<typeof proposalResponseSchema>;
export type ProposalCheck = z.infer<typeof proposalCheckSchema>;
export type ProposalRecord = z.infer<typeof proposalRecordSchema>;
