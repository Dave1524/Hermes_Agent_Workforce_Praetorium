import type { UsageItem } from "@/api/schemas/usage";
import { type Cost, type Measurement, type Usage, costFromCamel, usageFromCamel } from "./measurement";

export interface AgentUsage {
  agent: string;
  runs: number | null;
  usage: Measurement<Usage>;
  cost: Measurement<Cost>;
}

export interface CostTotal {
  amount: number | null;
  currency: string | null;
  measured: number;
  unmeasured: number;
}

export const toAgentUsage = (u: UsageItem): AgentUsage => ({
  agent: u.agent,
  runs: u.runCount ?? null,
  usage: usageFromCamel(u.usage),
  cost: costFromCamel(u.cost),
});

export const totalCost = (rows: AgentUsage[]): CostTotal => {
  const costs = rows.flatMap((r) => (r.cost.status === "measured" ? [r.cost.value] : []));
  if (costs.length === 0) return { amount: null, currency: null, measured: 0, unmeasured: rows.length };
  const amount = Math.round(costs.reduce((sum, c) => sum + c.amount, 0) * 100) / 100;
  return { amount, currency: costs[0]!.currency, measured: costs.length, unmeasured: rows.length - costs.length };
};
