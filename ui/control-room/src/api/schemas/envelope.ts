import { z } from "zod";
import { dataStatusSchema } from "./dataStatus";

export const envelope = <T extends z.ZodType>(items: T) =>
  z.object({
    apiVersion: z.string(),
    generatedAt: z.string(),
    dataStatus: dataStatusSchema,
    items,
  });
