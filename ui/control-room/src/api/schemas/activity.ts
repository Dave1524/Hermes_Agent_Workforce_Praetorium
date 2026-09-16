import { z } from "zod";
import { envelope } from "./envelope";

export const activityItemSchema = z.object({
  id: z.string(),
  time: z.string().nullish(),
  type: z.string().nullish(),
  actor: z.string().nullish(),
  event: z.string().nullish(),
  runId: z.string().nullish(),
  status: z.string().nullish(),
  handoff: z.unknown().nullish(),
});

export const activityResponseSchema = envelope(z.array(activityItemSchema));

export type ActivityItem = z.infer<typeof activityItemSchema>;
