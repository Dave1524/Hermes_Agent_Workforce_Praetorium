import type { CostCamel, CostSnake, UsageCamel, UsageSnake } from "@/api/schemas/measurement";

export type Measurement<T> = { status: "measured"; value: T } | { status: "unavailable" } | { status: "unknown" };

export interface Usage {
  input: number;
  output: number;
  cache: number;
  total: number;
}

export interface Cost {
  amount: number;
  currency: string;
}

const UNAVAILABLE = { status: "unavailable" } as const;
const UNKNOWN = { status: "unknown" } as const;

const measure = <T>(status: string | null | undefined, value: T | null): Measurement<T> => {
  if (status === "unavailable") return UNAVAILABLE;
  if (status === "measured" && value !== null) return { status: "measured", value };
  return UNKNOWN;
};

const usageValue = (total: number | null | undefined, input?: number | null, output?: number | null, cache?: number | null): Usage | null =>
  typeof total === "number" ? { input: input ?? 0, output: output ?? 0, cache: cache ?? 0, total } : null;

const costValue = (amount: number | null | undefined, currency: string | null | undefined): Cost | null =>
  typeof amount === "number" ? { amount, currency: currency ?? "USD" } : null;

export const usageFromSnake = (u: UsageSnake | null | undefined): Measurement<Usage> =>
  measure(u?.status, usageValue(u?.total_tokens, u?.input_tokens, u?.output_tokens, u?.cache_tokens));

export const usageFromCamel = (u: UsageCamel | null | undefined): Measurement<Usage> =>
  measure(u?.status, usageValue(u?.totalTokens, u?.inputTokens, u?.outputTokens, u?.cacheTokens));

export const costFromSnake = (c: CostSnake | null | undefined): Measurement<Cost> => measure(c?.status, costValue(c?.amount, c?.currency));

export const costFromCamel = (c: CostCamel | null | undefined): Measurement<Cost> => measure(c?.status, costValue(c?.amount, c?.currency));

export const measured = <T>(m: Measurement<T>): T | null => (m.status === "measured" ? m.value : null);
