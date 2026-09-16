import type { Outcome } from "@/model/outcome";

const STYLE: Record<Outcome, string> = {
  artifact: "text-green bg-green-dim",
  decline: "text-text-2 bg-surface-3",
  failed: "text-red bg-red-dim",
  skipped: "text-muted bg-surface-3",
  running: "text-blue bg-blue-dim",
  unknown: "text-muted bg-surface-3",
};

export default function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return <span className={`font-mono px-1.5 py-0.5 rounded text-[10px] ${STYLE[outcome]}`} data-outcome={outcome}>{outcome}</span>;
}
