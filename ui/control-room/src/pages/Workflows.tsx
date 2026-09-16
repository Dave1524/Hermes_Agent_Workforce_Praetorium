import { useMemo, useState } from "react";
import { workflowListResponseSchema } from "@/api/schemas/workflow";
import ControlStateBadge from "@/components/ControlStateBadge";
import DataStatusStrip from "@/components/DataStatusStrip";
import HealthBadge from "@/components/HealthBadge";
import { CostCell, UsageCell } from "@/components/MeasurementCell";
import OutcomeBadge from "@/components/OutcomeBadge";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { CONTROL_STATES } from "@/model/controlState";
import { HEALTHS } from "@/model/health";
import { formatCadence } from "@/model/time";
import { type WorkflowRow, toWorkflowRow } from "@/model/workflowRow";
import { usePageResource } from "@/shell/usePageResource";

const ALL = "all";

interface Filters {
  health: string;
  owner: string;
  control: string;
  search: string;
}

const matches = (row: WorkflowRow, f: Filters): boolean =>
  (f.health === ALL || row.health === f.health) &&
  (f.owner === ALL || row.owner === f.owner) &&
  (f.control === ALL || row.controlState === f.control) &&
  (f.search === "" || `${row.name} ${row.id}`.toLowerCase().includes(f.search.toLowerCase()));

export default function Workflows() {
  const workflows = usePageResource("/api/v1/workflows", workflowListResponseSchema);
  const [filters, setFilters] = useState<Filters>({ health: ALL, owner: ALL, control: ALL, search: "" });
  const rows = useMemo(() => (workflows.data?.items ?? []).map(toWorkflowRow), [workflows.data]);
  const owners = useMemo(() => [...new Set(rows.flatMap((r) => (r.owner ? [r.owner] : [])))].sort(), [rows]);

  if (workflows.status === "error" && workflows.error) return <ErrorNotice what="the workflows" error={workflows.error} onRetry={workflows.refresh} />;
  if (!workflows.data) return <Loading what="the workflows" />;
  const filtered = rows.filter((r) => matches(r, filters));
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <>
      <DataStatusStrip status={workflows.data.dataStatus} />
      <div className="p-6 max-w-[1200px] mx-auto">
        <div className="flex items-center gap-3 mb-5 flex-wrap">
          <input
            value={filters.search}
            onChange={(e) => set({ search: e.target.value })}
            placeholder="Filter workflows…"
            aria-label="Filter workflows"
            className="bg-surface border border-border rounded px-3 py-1.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-border-2 w-48"
          />
          <FilterSelect label="Health" value={filters.health} onChange={(health) => set({ health })} options={[ALL, ...HEALTHS]} allLabel="All health" />
          <FilterSelect label="Owner" value={filters.owner} onChange={(owner) => set({ owner })} options={[ALL, ...owners]} allLabel="All owners" />
          <FilterSelect label="Control" value={filters.control} onChange={(control) => set({ control })} options={[ALL, ...CONTROL_STATES]} allLabel="All control states" />
          <span className="text-xs text-muted ml-auto font-mono" data-testid="workflow-count">
            {filtered.length} of {rows.length} workflows
          </span>
        </div>

        <div className="bg-surface border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
                <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
                <th className="text-left px-4 py-2.5 font-medium">Owner</th>
                <th className="text-left px-4 py-2.5 font-medium">Health</th>
                <th className="text-left px-4 py-2.5 font-medium">Control</th>
                <th className="text-left px-4 py-2.5 font-medium hidden lg:table-cell">Last run</th>
                <th className="text-left px-4 py-2.5 font-medium hidden xl:table-cell">Next run</th>
                <th className="text-left px-4 py-2.5 font-medium hidden xl:table-cell">Cadence</th>
                <th className="text-right px-4 py-2.5 font-medium hidden lg:table-cell">Tokens</th>
                <th className="text-right px-4 py-2.5 font-medium hidden lg:table-cell">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((row) => (
                <tr key={row.id} className="hover:bg-surface-3 transition-colors">
                  <td className="px-4 py-3">
                    <RouteLink to={{ name: "workflow", id: row.id }} className="font-medium text-text hover:text-accent">{row.name}</RouteLink>
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
                  <td className="px-4 py-3 text-right hidden lg:table-cell"><UsageCell usage={row.usage} /></td>
                  <td className="px-4 py-3 text-right hidden lg:table-cell"><CostCell cost={row.cost} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <div className="p-8 text-center text-text-2 text-sm">No workflows match the current filters.</div>}
        </div>
      </div>
    </>
  );
}

function FilterSelect({ label, value, onChange, options, allLabel }: { label: string; value: string; onChange: (v: string) => void; options: readonly string[]; allLabel: string }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-surface border border-border rounded px-2.5 py-1.5 text-sm text-text-2 focus:outline-none focus:border-border-2 cursor-pointer"
      aria-label={label}
    >
      {options.map((o) => (
        <option key={o} value={o} className="bg-surface-2">{o === ALL ? allLabel : o}</option>
      ))}
    </select>
  );
}
