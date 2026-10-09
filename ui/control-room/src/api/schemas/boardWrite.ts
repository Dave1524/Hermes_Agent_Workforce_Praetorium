import { z } from "zod";

export const boardWriteResponseSchema = z.object({
  ok: z.boolean(),
  card: z.string().nullish(),
  error: z.string().nullish(),
  view: z.object({ rev: z.number() }).passthrough().nullish(),
});

export type BoardWriteResponse = z.infer<typeof boardWriteResponseSchema>;
export type BoardWriteRequest = { verb: "create" | "brief" | "note" | "edit" } & Record<string, unknown>;
