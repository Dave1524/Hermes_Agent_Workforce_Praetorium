import { z } from "zod";
import { costCamelSchema, usageCamelSchema } from "./measurement";
import { envelope } from "./envelope";

export const usageItemSchema = z.object({
  agent: z.string(),
  runCount: z.number().nullish(),
  usage: usageCamelSchema.nullish(),
  cost: costCamelSchema.nullish(),
});

export const usageResponseSchema = envelope(z.array(usageItemSchema));

export type UsageItem = z.infer<typeof usageItemSchema>;
