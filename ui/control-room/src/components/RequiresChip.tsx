import { type RequirementView, type RequiresStatus, firstUnsatisfied, requiresStatus } from "@/model/requires";

const STYLE: Record<RequiresStatus, string> = {
  satisfied: "text-green bg-green-dim border-green/20",
  down: "text-red bg-red-dim border-red/20",
  unknown: "text-muted bg-surface-3 border-border",
};

const label = (status: RequiresStatus, requires: RequirementView[]): string => {
  if (status === "down") return `requires down: ${firstUnsatisfied(requires)?.unit ?? ""}`;
  return status === "satisfied" ? "requires ok" : "requires unknown";
};

export default function RequiresChip({ requires }: { requires: RequirementView[] }) {
  if (requires.length === 0) return null;
  const status = requiresStatus(requires);
  const title = requires.map((r) => `${r.unit}: ${r.state}`).join("\n");
  return (
    <span className={`font-mono px-1.5 py-0.5 rounded border text-[10px] whitespace-nowrap ${STYLE[status]}`} data-testid="requires-chip" data-requires={status} title={title}>
      {label(status, requires)}
    </span>
  );
}
