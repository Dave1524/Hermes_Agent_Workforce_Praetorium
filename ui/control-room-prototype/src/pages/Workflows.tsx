import React, { useState } from "react";
import { WORKFLOWS } from "../data";
import type { Health, Lifecycle } from "../data";
import HealthBadge from "../components/HealthBadge";

interface Props {
  onNavigate: (page: string, workflowId?: string) => void;
}

const AGENTS = ["All", "Marcus", "Claudius", "Augustus", "Trajan", "Aurelian"];
const LIFECYCLES = ["All", "active", "paused", "retired"];
const HEALTHS: (Health | "all")[] = ["all", "healthy", "running", "incomplete", "attention", "failed", "paused"];

export default function Workflows({ onNavigate }: Props) {
  const [filterHealth, setFilterHealth] = useState<string>("all");
  const [filterAgent, setFilterAgent] = useState("All");
  const [filterLifecycle, setFilterLifecycle] = useState("All");
  const [expandedTriggers, setExpandedTriggers] = useState<string[]>([]);
  const [search, setSearch] = useState("");

  const filtered = WORKFLOWS.filter((w) => {
    if (filterHealth !== "all" && w.health !== filterHealth) return false;
    if (filterAgent !== "All" && w.agent !== filterAgent) return false;
    if (filterLifecycle !== "All" && w.lifecycle !== filterLifecycle) return false;
    if (search && !w.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const toggleTriggers = (id: string) => {
    setExpandedTriggers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };

  return (
    <div className="p-6 max-w-[1200px] mx-auto">
      {/* Filters */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter workflows…"
          className="bg-surface border border-border rounded px-3 py-1.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-border-2 w-48"
        />
        <FilterSelect label="Health" value={filterHealth} onChange={setFilterHealth} options={HEALTHS.map((h) => ({ value: h, label: h === "all" ? "All health" : h }))} />
        <FilterSelect label="Agent" value={filterAgent} onChange={setFilterAgent} options={AGENTS.map((a) => ({ value: a, label: a }))} />
        <FilterSelect label="Lifecycle" value={filterLifecycle} onChange={setFilterLifecycle} options={LIFECYCLES.map((l) => ({ value: l, label: l === "All" ? "All lifecycle" : l }))} />
        <span className="text-xs text-muted ml-auto">{filtered.length} workflows</span>
      </div>

      {/* Table */}
      <div className="bg-surface border border-border rounded-md overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted">
              <th className="text-left px-4 py-2.5 font-medium w-8"></th>
              <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
              <th className="text-left px-4 py-2.5 font-medium">Agent</th>
              <th className="text-left px-4 py-2.5 font-medium hidden lg:table-cell">Purpose</th>
              <th className="text-left px-4 py-2.5 font-medium">Health</th>
              <th className="text-left px-4 py-2.5 font-medium hidden xl:table-cell">Last run</th>
              <th className="text-left px-4 py-2.5 font-medium hidden xl:table-cell">Next run</th>
              <th className="text-left px-4 py-2.5 font-medium hidden xl:table-cell">Latest output</th>
              <th className="text-right px-4 py-2.5 font-medium">Reliability</th>
              <th className="text-right px-4 py-2.5 font-medium hidden lg:table-cell">Tokens</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((wf) => (
              <React.Fragment key={wf.id}>
                <tr
                  className="hover:bg-surface-3 transition-colors cursor-pointer"
                  onClick={() => onNavigate("workflow-detail", wf.id)}
                >
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleTriggers(wf.id); }}
                      className="text-muted text-xs hover:text-text-2 transition-colors"
                      aria-label="Toggle triggers"
                    >
                      {expandedTriggers.includes(wf.id) ? "▾" : "▸"}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-text">{wf.name}</span>
                  </td>
                  <td className="px-4 py-3 text-text-2">{wf.agent}</td>
                  <td className="px-4 py-3 text-text-2 text-xs max-w-[220px] truncate hidden lg:table-cell">{wf.purpose}</td>
                  <td className="px-4 py-3"><HealthBadge health={wf.health} /></td>
                  <td className="px-4 py-3 text-muted font-mono text-xs hidden xl:table-cell">{wf.lastRun}</td>
                  <td className="px-4 py-3 text-muted font-mono text-xs hidden xl:table-cell">{wf.nextRun}</td>
                  <td className="px-4 py-3 text-text-2 text-xs max-w-[140px] truncate hidden xl:table-cell">{wf.latestOutput}</td>
                  <td className="px-4 py-3 text-right">
                    <ReliabilityBar pct={wf.reliability7d} />
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-text-2 hidden lg:table-cell">{wf.tokens}</td>
                </tr>
                {expandedTriggers.includes(wf.id) && (
                  <tr key={`${wf.id}-triggers`} className="bg-surface-2">
                    <td />
                    <td colSpan={9} className="px-4 py-3">
                      <div className="text-xs text-text-2 space-y-1.5">
                        <p className="text-muted font-medium uppercase tracking-wider text-[10px] mb-2">Triggers & schedules</p>
                        <div className="flex items-center gap-3 font-mono">
                          <span className="text-accent">①</span>
                          <span>{wf.trigger}</span>
                          <span className="text-muted">·</span>
                          <span>Timezone: Europe/London</span>
                          <span className="text-muted">·</span>
                          <span>Catch-up: disabled</span>
                        </div>
                        <div className="flex items-center gap-3 font-mono mt-1">
                          <span className="text-muted">Eligibility:</span>
                          <span>No eligibility constraints</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="p-8 text-center text-text-2 text-sm">No workflows match the current filters.</div>
        )}
      </div>
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-surface border border-border rounded px-2.5 py-1.5 text-sm text-text-2 focus:outline-none focus:border-border-2 cursor-pointer"
      aria-label={label}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-surface-2">{o.label}</option>
      ))}
    </select>
  );
}

function ReliabilityBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? "bg-green" : pct >= 75 ? "bg-amber" : "bg-red";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="w-16 h-1.5 bg-surface-3 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-text-2 w-9 text-right">{pct}%</span>
    </div>
  );
}
