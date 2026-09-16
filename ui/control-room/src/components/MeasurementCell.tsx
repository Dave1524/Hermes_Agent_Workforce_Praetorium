import type { Cost, Measurement, Usage } from "@/model/measurement";
import { formatCost, formatUsage } from "@/model/tokens";

const NOTE: Record<"unavailable" | "unknown", string> = {
  unavailable: "The runtime did not record this. Shown as unavailable rather than as zero.",
  unknown: "The API returned a status this screen does not know.",
};

export function NotMeasured({ status }: { status: "unavailable" | "unknown" }) {
  return (
    <span className="text-xs font-mono text-muted border border-border rounded px-1.5 py-0.5" title={NOTE[status]}>
      {status}
    </span>
  );
}

export function UsageCell({ usage }: { usage: Measurement<Usage> }) {
  if (usage.status !== "measured") return <NotMeasured status={usage.status} />;
  return <span className="font-mono text-xs text-text">{formatUsage(usage)}</span>;
}

export function CostCell({ cost }: { cost: Measurement<Cost> }) {
  if (cost.status !== "measured") return <NotMeasured status={cost.status} />;
  return <span className="font-mono text-xs text-text-2">{formatCost(cost)}</span>;
}
