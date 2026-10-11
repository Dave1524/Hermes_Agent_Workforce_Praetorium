import { z } from "zod";

export const boardWriteResponseSchema = z.object({
  ok: z.boolean(),
  card: z.string().nullish(),
  error: z.string().nullish(),
  view: z.object({ rev: z.number(), brief_hash: z.string().nullish() }).passthrough().nullish(),
});

export type BoardWriteResponse = z.infer<typeof boardWriteResponseSchema>;
export const DECISION_VERBS = ["approve_brief", "return_brief", "approve", "request_changes", "reject", "withdraw", "block", "unblock"] as const;
export type DecisionVerb = (typeof DECISION_VERBS)[number];
export type BoardWriteRequest = { verb: "create" | "brief" | "note" | "edit" | DecisionVerb } & Record<string, unknown>;
