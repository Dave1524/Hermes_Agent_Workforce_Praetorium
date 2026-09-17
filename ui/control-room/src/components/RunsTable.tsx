import ClosedChip from "@/components/ClosedChip";
import { CostCell, UsageCell } from "@/components/MeasurementCell";
import OutcomeBadge from "@/components/OutcomeBadge";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import type { Run } from "@/model/run";
import { formatDuration } from "@/model/time";

export default function RunsTable({ runs, empty = "No runs recorded." }: { runs: Run[]; empty?: string }) {
  if (runs.length === 0) return <p className="text-xs text-muted">{empty}</p>;
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted border-b border-border">
          <th className="text-left py-1.5 font-medium">Run</th>
          <th className="text-left py-1.5 font-medium">Outcome</th>
          <th className="text-left py-1.5 font-medium">Ended</th>
          <th className="text-left py-1.5 font-medium">Duration</th>
          <th className="text-right py-1.5 font-medium">Tokens</th>
          <th className="text-right py-1.5 font-medium">Cost</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {runs.map((run) => (
          <tr key={run.id} className="hover:bg-surface-3 transition-colors">
            <td className="py-2 font-mono">{run.id ? <RouteLink to={{ name: "run", id: run.id }} className="text-accent hover:underline">{run.id}</RouteLink> : "—"}</td>
            <td className="py-2"><span className="inline-flex items-center gap-1.5"><OutcomeBadge outcome={run.outcome} /><ClosedChip closed={run.closed} /></span></td>
            <td className="py-2"><When iso={run.endedAt} /></td>
            <td className="py-2 font-mono text-muted">{formatDuration(run.durationSeconds) ?? "—"}</td>
            <td className="py-2 text-right"><UsageCell usage={run.usage} /></td>
            <td className="py-2 text-right"><CostCell cost={run.cost} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
