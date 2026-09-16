import { useState } from "react";
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { WORKFLOWS, INCIDENTS, AGENT_USAGE, RECENT_OUTPUTS, RELIABILITY_7D } from "../data";
import HealthBadge from "../components/HealthBadge";

interface Props {
  onNavigate: (page: string, workflowId?: string) => void;
}

export default function Overview({ onNavigate }: Props) {
  const [expandedOutput, setExpandedOutput] = useState<string | null>(null);
  const [outputActions, setOutputActions] = useState<Record<string, string>>({});
  const [acknowledgedIncidents, setAcknowledgedIncidents] = useState<string[]>([]);

  const openIncidents = INCIDENTS.filter((i) => i.status === "open" && !acknowledgedIncidents.includes(i.id));

  const handleOutputAction = (id: string, action: string) => {
    setOutputActions((prev) => ({ ...prev, [id]: action }));
  };

  const totalTokens = AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.totalTokens ?? 0), 0);
  const totalCost = AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.cost ?? 0), 0);

  return (
    <div className="p-6 max-w-[1200px] mx-auto space-y-6">
      {/* Status summary */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Workflows", value: "30", icon: "⬡", color: "text-text-2" },
          { label: "Healthy", value: "24", icon: "✓", color: "text-green" },
          { label: "Running", value: "2", icon: "▶", color: "text-blue" },
          { label: "Attention", value: "2", icon: "!", color: "text-amber" },
          { label: "Paused", value: "2", icon: "⏸", color: "text-muted" },
        ].map((s) => (
          <div key={s.label} className="bg-surface border border-border rounded-md px-4 py-3 flex items-center gap-3">
            <span className={`text-lg leading-none ${s.color}`} aria-hidden>{s.icon}</span>
            <div>
              <div className={`text-2xl font-semibold leading-none ${s.color}`}>{s.value}</div>
              <div className="text-text-2 text-xs mt-1">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Needs attention */}
        <div className="col-span-2 space-y-3">
          <SectionHeader title="Needs attention" count={openIncidents.length} countColor="bg-amber text-bg" />
          {openIncidents.length === 0 ? (
            <div className="bg-surface border border-border rounded-md p-6 text-center text-text-2 text-sm">
              <span className="text-green text-lg block mb-2">✓</span>
              No open incidents — all workflows healthy.
            </div>
          ) : (
            openIncidents.map((inc) => (
              <div key={inc.id} className="bg-surface border border-border rounded-md p-4">
                <div className="flex items-start gap-3">
                  <SeverityDot severity={inc.severity} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-text">{inc.workflow}</span>
                      <span className="text-muted text-xs">·</span>
                      <span className="text-text-2 text-xs">{inc.agent}</span>
                    </div>
                    <p className="text-sm text-text-2 mt-1">{inc.issue}</p>
                    <div className="flex items-center gap-3 mt-2">
                      <span className="text-xs text-muted font-mono">{inc.duration} open</span>
                      <span className="text-xs text-text-2">{inc.action}</span>
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => setAcknowledgedIncidents((p) => [...p, inc.id])}
                      className="px-2.5 py-1 text-xs border border-border rounded text-text-2 hover:bg-surface-3 transition-colors"
                    >
                      Ack
                    </button>
                    <button
                      onClick={() => onNavigate("workflow-detail", WORKFLOWS.find((w) => w.name === inc.workflow)?.id)}
                      className="px-2.5 py-1 text-xs bg-accent-dim border border-accent/20 rounded text-accent font-medium hover:bg-accent/20 transition-colors"
                    >
                      Investigate
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Reliability chart */}
        <div className="space-y-3">
          <SectionHeader title="7-day reliability" />
          <div className="bg-surface border border-border rounded-md p-4">
            <div className="mb-3 flex items-baseline justify-between">
              <span className="text-text text-sm font-medium">Valid outputs / eligible runs</span>
            </div>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={RELIABILITY_7D} barCategoryGap="30%">
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#5e5e6a" }} axisLine={false} tickLine={false} />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="bg-surface-3 border border-border rounded px-2 py-1.5 text-xs font-mono">
                        <span className="text-text">{d.valid}/{d.eligible}</span>{" "}
                        <span className="text-text-2">valid</span>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="eligible" fill="#2a2a32" radius={[2, 2, 0, 0]} />
                <Bar dataKey="valid" fill="#3ea862" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-3 text-xs text-text-2">
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-green inline-block" />Valid</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-border inline-block" />Eligible</span>
            </div>
          </div>

          {/* Agent usage compact */}
          <SectionHeader title="Agent usage today" />
          <div className="bg-surface border border-border rounded-md divide-y divide-border">
            {AGENT_USAGE.map((a) => (
              <div key={a.name} className="px-4 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AgentAvatar name={a.name} size="sm" />
                  <span className="text-sm text-text">{a.name}</span>
                </div>
                {a.available ? (
                  <div className="text-right">
                    <div className="text-xs font-mono text-text">{fmtTokens(a.totalTokens!)}</div>
                    <div className="text-xs font-mono text-muted">${a.cost!.toFixed(2)}</div>
                  </div>
                ) : (
                  <Unavailable />
                )}
              </div>
            ))}
            <div className="px-4 py-2.5 flex justify-between text-xs font-mono text-text-2 bg-surface-3">
              <span>Total (available agents)</span>
              <span className="text-text">{fmtTokens(totalTokens)} · ${totalCost.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent outputs */}
      <div>
        <SectionHeader title="Recent outputs" />
        <div className="bg-surface border border-border rounded-md mt-3 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
                <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
                <th className="text-left px-4 py-2.5 font-medium">Output</th>
                <th className="text-left px-4 py-2.5 font-medium">Created</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-right px-4 py-2.5 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {RECENT_OUTPUTS.map((out) => {
                const action = outputActions[out.id];
                return (
                  <tr key={out.id} className="hover:bg-surface-3 transition-colors">
                    <td className="px-4 py-3 text-text-2">{out.workflow}</td>
                    <td className="px-4 py-3 text-text font-medium">{out.title}</td>
                    <td className="px-4 py-3 text-muted font-mono text-xs">{out.createdAt}</td>
                    <td className="px-4 py-3">
                      <OutputStatusBadge status={action ?? out.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <a href={out.notionUrl} className="px-2.5 py-1 text-xs bg-accent-dim border border-accent/20 text-accent rounded hover:bg-accent/20 transition-colors font-medium">
                          Open in Notion
                        </a>
                        {expandedOutput === out.id ? (
                          <>
                            {["Approve", "Reject", "Edit", "Send", "Assign", "Archive"].map((act) => (
                              <button
                                key={act}
                                onClick={() => { handleOutputAction(out.id, act.toLowerCase()); setExpandedOutput(null); }}
                                className="px-2 py-1 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors"
                              >
                                {act}
                              </button>
                            ))}
                            <button onClick={() => setExpandedOutput(null)} className="text-muted text-xs px-1">✕</button>
                          </>
                        ) : (
                          <button
                            onClick={() => setExpandedOutput(out.id)}
                            className="px-2 py-1 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors"
                          >
                            ···
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ title, count, countColor }: { title: string; count?: number; countColor?: string }) {
  return (
    <div className="flex items-center gap-2">
      <h2 className="text-sm font-semibold text-text">{title}</h2>
      {count !== undefined && (
        <span className={`text-xs font-mono rounded-full px-1.5 py-0.5 ${countColor ?? "bg-surface-3 text-text-2"}`}>{count}</span>
      )}
    </div>
  );
}

function SeverityDot({ severity }: { severity: string }) {
  const colors: Record<string, string> = { high: "bg-red", medium: "bg-amber", low: "bg-blue" };
  const labels: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };
  return (
    <div className="flex flex-col items-center gap-1 pt-0.5">
      <span className={`w-2 h-2 rounded-full shrink-0 ${colors[severity] ?? "bg-gray"}`} aria-label={`${labels[severity]} severity`} />
    </div>
  );
}

export function AgentAvatar({ name, size = "sm" }: { name: string; size?: "sm" | "md" }) {
  const colors: Record<string, string> = {
    Marcus: "bg-blue-dim text-blue", Trajan: "bg-green-dim text-green",
    Claudius: "bg-amber-dim text-amber", Augustus: "bg-accent-dim text-accent",
    Aurelian: "bg-surface-3 text-muted",
  };
  const sz = size === "md" ? "w-7 h-7 text-xs" : "w-5 h-5 text-[10px]";
  return (
    <div className={`rounded-full flex items-center justify-center font-semibold shrink-0 ${sz} ${colors[name] ?? "bg-surface-3 text-text-2"}`}>
      {name[0]}
    </div>
  );
}

function OutputStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    approved: "text-green bg-green-dim", pending: "text-amber bg-amber-dim",
    rejected: "text-red bg-red-dim", draft: "text-text-2 bg-surface-3",
    approve: "text-green bg-green-dim", reject: "text-red bg-red-dim",
    edit: "text-blue bg-blue-dim", send: "text-green bg-green-dim",
    assign: "text-text-2 bg-surface-3", archive: "text-muted bg-surface-3",
  };
  return (
    <span className={`text-[11px] font-mono px-2 py-0.5 rounded capitalize ${map[status] ?? "text-text-2 bg-surface-3"}`}>
      {status}
    </span>
  );
}

export function Unavailable() {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <button
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className="text-xs font-mono text-muted border border-border rounded px-2 py-0.5"
      >
        Unavailable
      </button>
      {show && (
        <div className="absolute right-0 bottom-full mb-1.5 w-56 bg-surface-3 border border-border rounded p-2.5 text-xs text-text-2 z-10 shadow-lg">
          Runtime did not provide trustworthy usage data. This value is not shown rather than displayed as zero.
        </div>
      )}
    </div>
  );
}

function fmtTokens(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
