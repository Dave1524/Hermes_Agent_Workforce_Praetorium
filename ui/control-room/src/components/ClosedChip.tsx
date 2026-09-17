import type { RunClosure } from "@/model/run";

export default function ClosedChip({ closed }: { closed: RunClosure | null }) {
  if (!closed) return null;
  return (
    <span className="font-mono px-1.5 py-0.5 rounded border text-[10px] text-text-2 bg-surface-3 border-border whitespace-nowrap" data-testid="closed-chip" title={`${closed.by}: ${closed.reason}`}>
      closed
    </span>
  );
}
