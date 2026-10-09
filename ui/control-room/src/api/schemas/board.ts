import { z } from "zod";
import { envelope } from "./envelope";

export const cardSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  column: z.string(),
  scheduled: z.boolean().default(false),
  outcome: z.string().nullish(),
  blockedCause: z.string().nullish(),
  approvedLanding: z.boolean().default(false),
  owner: z.string(),
  kind: z.string(),
  priority: z.string().nullish(),
  tags: z.array(z.string()).default([]),
  deadline: z.string().nullish(),
  researchOn: z.string().nullish(),
  briefVersion: z.number().default(0),
  exceptions: z.array(z.string()).default([]),
});

export const boardSchema = z.object({
  columns: z.array(z.string()),
  cards: z.array(cardSummarySchema),
});

export const cardFieldsSchema = z.object({
  title: z.string(),
  idea: z.string(),
  scope: z.array(z.string()).default([]),
  deadline: z.string().nullish(),
  research_on: z.string().nullish(),
  priority: z.string().nullish(),
  tags: z.array(z.string()).default([]),
});

export const cardBriefSchema = z.object({
  text: z.string().nullish(),
  hash: z.string(),
  version: z.number(),
  by: z.string(),
  ts: z.string().nullish(),
  approved: z.boolean(),
  approvedAt: z.string().nullish(),
  current: z.boolean(),
});

export const cardRunSchema = z.object({
  runId: z.string(),
  workflow: z.string().nullish(),
  ts: z.string().nullish(),
  purpose: z.string(),
  outcome: z.string().nullish(),
  page: z.string().nullish(),
  void: z.boolean().default(false),
});

export const cardActivitySchema = z.object({
  ts: z.string().nullish(),
  kind: z.string(),
  actor: z.string(),
  runId: z.string().nullish(),
  detail: z.string().nullish(),
  outcome: z.string().nullish(),
});

export const acceptanceLineSchema = z.object({
  line: z.string(),
  answer: z.string().nullish(),
  note: z.string().nullish(),
});

export const cardResearchSchema = z.object({
  status: z.string(),
  reason: z.string().nullish(),
  url: z.string().nullish(),
  text: z.string().nullish(),
  pageHash: z.string().nullish(),
  publishedHash: z.string().nullish(),
  changed: z.boolean().nullish(),
  acceptance: z.array(acceptanceLineSchema).default([]),
});

export const cardDetailSchema = cardSummarySchema.extend({
  fields: cardFieldsSchema,
  rev: z.number(),
  editable: z.array(z.string()).default([]),
  moves: z.array(z.string()).default([]),
  locked: z.array(z.string()).default([]),
  brief: cardBriefSchema.nullish(),
  runs: z.array(cardRunSchema).default([]),
  activity: z.array(cardActivitySchema).default([]),
  research: cardResearchSchema,
});

export const boardResponseSchema = envelope(boardSchema);
export const cardResponseSchema = envelope(cardDetailSchema);

export type CardSummary = z.infer<typeof cardSummarySchema>;
export type CardDetail = z.infer<typeof cardDetailSchema>;
export type Board = z.infer<typeof boardSchema>;
export type CardActivity = z.infer<typeof cardActivitySchema>;
export type CardResearch = z.infer<typeof cardResearchSchema>;
