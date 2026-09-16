import type { RuntimeStatus, RuntimeView } from "@/model/agent";
import When from "./When";

const STYLE: Record<RuntimeStatus, string> = {
  up: "text-green bg-green-dim border-green/20",
  down: "text-red bg-red-dim border-red/20",
  unknown: "text-muted bg-surface-3 border-border",
};

export default function RuntimeChip({ runtime }: { runtime: RuntimeView }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`font-mono px-1.5 py-0.5 rounded border text-[10px] ${STYLE[runtime.status]}`} data-testid="runtime-chip" data-runtime={runtime.status} title={runtime.unit ?? undefined}>
        {runtime.state}
      </span>
      {runtime.since && <span className="text-[10px] text-muted">since <When iso={runtime.since} /></span>}
    </span>
  );
}
