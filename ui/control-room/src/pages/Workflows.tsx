import { useMemo, useState } from "react";
import { workflowListResponseSchema } from "@/api/schemas/workflow";
import DataStatusStrip from "@/components/DataStatusStrip";
import FilterSelect, { ALL } from "@/components/FilterSelect";
import { SectionHeader } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import WorkflowTable from "@/components/WorkflowTable";
import { CONTROL_STATES } from "@/model/controlState";
import { HEALTHS } from "@/model/health";
import type { Role } from "@/model/role";
import { type WorkflowRow, toWorkflowRow } from "@/model/workflowRow";
import { usePageResource } from "@/shell/usePageResource";

interface Filters {
  health: string;
  owner: string;
  control: string;
  search: string;
}

interface Section {
  role: Role;
  title: string;
  measurements: boolean;
}

// Runtimes never list here (the Agents view owns them); a role this screen does not know gets its own section rather than a guess.
const SECTIONS: readonly Section[] = [
  { role: "agent-workflow", title: "Agent workflows", measurements: true },
  { role: "system-workflow", title: "System workflows", measurements: false },
  { role: "unknown", title: "Workflows of unknown role", measurements: true },
];

const matches = (row: WorkflowRow, f: Filters): boolean =>
  (f.health === ALL || row.health === f.health) &&
  (f.owner === ALL || row.owner === f.owner) &&
  (f.control === ALL || row.controlState === f.control) &&
  (f.search === "" || `${row.name} ${row.id}`.toLowerCase().includes(f.search.toLowerCase()));

export default function Workflows() {
  const workflows = usePageResource("/api/v1/workflows", workflowListResponseSchema);
  const [filters, setFilters] = useState<Filters>({ health: ALL, owner: ALL, control: ALL, search: "" });
  const rows = useMemo(() => (workflows.data?.items ?? []).map(toWorkflowRow).filter((r) => r.role !== "agent-runtime"), [workflows.data]);
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

        <div className="space-y-6">
          {SECTIONS.map((section) => <RoleSection key={section.role} section={section} all={rows} filtered={filtered} />)}
        </div>
      </div>
    </>
  );
}

function RoleSection({ section, all, filtered }: { section: Section; all: WorkflowRow[]; filtered: WorkflowRow[] }) {
  const total = all.filter((r) => r.role === section.role);
  if (total.length === 0 && section.role === "unknown") return null;
  const rows = filtered.filter((r) => r.role === section.role);
  return (
    <section data-testid={`section-${section.role}`}>
      <div className="flex items-center gap-3 mb-3">
        <SectionHeader title={section.title} />
        <span className="text-xs text-muted font-mono" data-testid="section-count">{rows.length} of {total.length}</span>
      </div>
      <WorkflowTable rows={rows} measurements={section.measurements} />
    </section>
  );
}
