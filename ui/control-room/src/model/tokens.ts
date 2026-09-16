import type { Cost, Measurement, Usage } from "./measurement";

export const formatTokens = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
};

export const formatUsage = (m: Measurement<Usage>): string => (m.status === "measured" ? formatTokens(m.value.total) : m.status);

const formatAmount = (c: Cost): string => (c.currency === "USD" ? `$${c.amount.toFixed(2)}` : `${c.amount.toFixed(2)} ${c.currency}`);

export const formatCost = (m: Measurement<Cost>): string => (m.status === "measured" ? formatAmount(m.value) : m.status);
