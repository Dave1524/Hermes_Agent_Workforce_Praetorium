import { z } from "zod";

// A measurement is measured or unavailable; its fields are null when unavailable and never 0.
// The workflow and run endpoints emit snake_case (the receipt's own keys), /api/v1/usage camelCase.
export const usageSnakeSchema = z.object({
  status: z.string(),
  input_tokens: z.number().nullish(),
  output_tokens: z.number().nullish(),
  cache_tokens: z.number().nullish(),
  total_tokens: z.number().nullish(),
});

export const costSnakeSchema = z.object({
  status: z.string(),
  amount: z.number().nullish(),
  currency: z.string().nullish(),
  source: z.string().nullish(),
  confidence: z.string().nullish(),
});

export const usageCamelSchema = z.object({
  status: z.string(),
  inputTokens: z.number().nullish(),
  outputTokens: z.number().nullish(),
  cacheTokens: z.number().nullish(),
  totalTokens: z.number().nullish(),
});

export const costCamelSchema = z.object({
  status: z.string(),
  amount: z.number().nullish(),
  currency: z.string().nullish(),
});

export type UsageSnake = z.infer<typeof usageSnakeSchema>;
export type CostSnake = z.infer<typeof costSnakeSchema>;
export type UsageCamel = z.infer<typeof usageCamelSchema>;
export type CostCamel = z.infer<typeof costCamelSchema>;
