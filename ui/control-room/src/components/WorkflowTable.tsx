import ControlStateBadge from "@/components/ControlStateBadge";
import GuardsChip from "@/components/GuardsChip";
import HealthBadge from "@/components/HealthBadge";
import { CostCell, UsageCell } from "@/components/MeasurementCell";
import OutcomeBadge from "@/components/OutcomeBadge";
import RequiresChip from "@/components/RequiresChip";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { formatCadence } from "@/model/time";
import type { WorkflowRow } from "@/model/workflowRow";

interface Props {
  rows: WorkflowRow[];
  // System workflows are scripts: their tokens and cost are always unavailable, so the columns are dropped.
  measurements: boolean;
}

const th = "text-left px-4 py-2.5 font-medium";

function WorkflowTableRow({ row, measurements }: { row: WorkflowRow; measurements: boolean }) {
  return (
    <tr className="hover:bg-surface-3 transition-colors" data-role={row.role} data-workflow-id={row.id}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <RouteLink to={{ name: "workflow", id: row.id }} className="font-medium text-text hover:text-accent">{row.name}</RouteLink>
          <RequiresChip requires={row.requires} />
          <GuardsChip guards={row.guards} />
        </div>
        <div className="text-[10px] font-mono text-muted">{row.id}</div>
      </td>
      <td className="px-4 py-3 text-text-2">{row.owner ?? <span className="text-muted">—</span>}</td>
      <td className="px-4 py-3"><HealthBadge health={row.health} /></td>
      <td className="px-4 py-3"><ControlStateBadge state={row.controlState} /></td>
      <td className="px-4 py-3 hidden lg:table-cell">
        <div className="flex items-center gap-2">
          <When iso={row.lastRunAt} />
          {row.lastOutcome !== "unknown" && <OutcomeBadge outcome={row.lastOutcome} />}
        </div>
      </td>
      <td className="px-4 py-3 hidden xl:table-cell"><When iso={row.nextRunAt} estimated={row.nextRunEstimated} /></td>
      <td className="px-4 py-3 font-mono text-xs text-text-2 hidden xl:table-cell" title={row.cadenceSpec ?? undefined}>{formatCadence(row.cadenceSeconds) ?? "—"}</td>
      {measurements && <td className="px-4 py-3 text-right hidden lg:table-cell"><UsageCell usage={row.usage} /></td>}
      {measurements && <td className="px-4 py-3 text-right hidden lg:table-cell"><CostCell cost={row.cost} /></td>}
    </tr>
  );
}

export default function WorkflowTable({ rows, measurements }: Props) {
  return (
    <div className="bg-surface border border-border rounded-md overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-muted">
            <th className={th}>Workflow</th>
            <th className={th}>Owner</th>
            <th className={th}>Health</th>
            <th className={th}>Control</th>
            <th className={`${th} hidden lg:table-cell`}>Last run</th>
            <th className={`${th} hidden xl:table-cell`}>Next run</th>
            <th className={`${th} hidden xl:table-cell`}>Cadence</th>
            {measurements && <th className="text-right px-4 py-2.5 font-medium hidden lg:table-cell">Tokens</th>}
            {measurements && <th className="text-right px-4 py-2.5 font-medium hidden lg:table-cell">Cost</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((row) => <WorkflowTableRow key={row.id} row={row} measurements={measurements} />)}
        </tbody>
      </table>
      {rows.length === 0 && <div className="p-8 text-center text-text-2 text-sm">No workflows match the current filters.</div>}
    </div>
  );
}
