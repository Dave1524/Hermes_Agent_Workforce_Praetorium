import { useState } from "react";
import { INCIDENTS } from "../data";
import type { Incident } from "../data";

interface Props {
  onNavigate: (page: string, workflowId?: string) => void;
}

export default function Incidents({ onNavigate }: Props) {
  const [tab, setTab] = useState<"open" | "acknowledged" | "resolved">("open");
  const [acknowledged, setAcknowledged] = useState<string[]>([]);

  const tabData: Record<string, Incident[]> = {
    open: INCIDENTS.filter((i) => i.status === "open" && !acknowledged.includes(i.id)),
    acknowledged: INCIDENTS.filter((i) => acknowledged.includes(i.id)),
    resolved: INCIDENTS.filter((i) => i.status === "resolved"),
  };

  const counts = {
    open: tabData.open.length,
    acknowledged: tabData.acknowledged.length,
    resolved: tabData.resolved.length,
  };

  return (
    <div className="p-6 max-w-[1000px] mx-auto">
      {/* Notification settings notice */}
      <div className="bg-surface border border-border rounded-md p-4 mb-5 text-xs text-text-2 flex items-start gap-3">
        <span className="text-accent text-base mt-0.5">🔔</span>
        <div className="space-y-1">
          <p><span className="text-text font-medium">Buzz notification rules:</span> Immediate notification only when Dave must act. Repeated observations are deduplicated. One daily digest contains all unresolved incidents. Recovery message sent when an incident closes.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-border mb-5">
        {(["open", "acknowledged", "resolved"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm capitalize border-b-2 -mb-px transition-colors ${
              tab === t
                ? "border-accent text-accent"
                : "border-transparent text-text-2 hover:text-text"
            }`}
          >
            {t}
            {counts[t] > 0 && (
              <span className={`ml-2 text-[10px] font-mono rounded-full px-1.5 py-0.5 ${
                t === "open" ? "bg-red text-white" : "bg-surface-3 text-text-2"
              }`}>{counts[t]}</span>
            )}
          </button>
        ))}
      </div>

      {/* Incidents */}
      <div className="space-y-3">
        {tabData[tab].length === 0 ? (
          <div className="bg-surface border border-border rounded-md p-8 text-center">
            <span className="text-green text-2xl block mb-2">✓</span>
            <p className="text-text-2 text-sm">No {tab} incidents.</p>
          </div>
        ) : (
          tabData[tab].map((inc) => (
            <IncidentCard
              key={inc.id}
              incident={inc}
              tab={tab}
              onAcknowledge={() => setAcknowledged((p) => [...p, inc.id])}
              onInvestigate={() => onNavigate("workflows")}
            />
          ))
        )}
      </div>
    </div>
  );
}

function IncidentCard({ incident: inc, tab, onAcknowledge, onInvestigate }: {
  incident: Incident; tab: string; onAcknowledge: () => void; onInvestigate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const sevColor = { high: "border-l-red", medium: "border-l-amber", low: "border-l-blue" }[inc.severity] ?? "border-l-border";
  const sevText = { high: "text-red", medium: "text-amber", low: "text-blue" }[inc.severity] ?? "text-muted";

  return (
    <div className={`bg-surface border border-border border-l-2 ${sevColor} rounded-md`}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={`text-[10px] font-mono font-medium uppercase ${sevText}`}>{inc.severity}</span>
              <span className="text-muted text-xs">·</span>
              <span className="font-medium text-sm text-text">{inc.workflow}</span>
              <span className="text-muted text-xs">·</span>
              <span className="text-text-2 text-xs">{inc.agent}</span>
            </div>
            <p className="text-sm text-text-2 mb-2">{inc.issue}</p>
            <div className="flex items-center gap-4 flex-wrap text-xs text-muted font-mono">
              <span>First seen: {inc.firstSeen}</span>
              <span>Last seen: {inc.lastSeen}</span>
              <span>Open: {inc.duration}</span>
              <span>Run: {inc.runId}</span>
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <button onClick={() => setExpanded((p) => !p)} className="px-2.5 py-1 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">
              {expanded ? "Less" : "Details"}
            </button>
            {tab === "open" && (
              <button onClick={onAcknowledge} className="px-2.5 py-1 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">
                Acknowledge
              </button>
            )}
            {tab !== "resolved" && (
              <button onClick={onInvestigate} className="px-2.5 py-1 text-xs bg-accent-dim border border-accent/20 text-accent rounded hover:bg-accent/20 transition-colors font-medium">
                Investigate
              </button>
            )}
            {tab === "resolved" && (
              <span className="px-2.5 py-1 text-xs bg-green-dim text-green rounded font-mono">Resolved</span>
            )}
          </div>
        </div>

        {expanded && (
          <div className="mt-4 pt-4 border-t border-border space-y-2 text-xs">
            <div className="flex gap-2">
              <span className="text-muted w-32 shrink-0">Required action</span>
              <span className="text-text-2">{inc.action}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted w-32 shrink-0">Buzz state</span>
              <span className="text-text-2">
                {tab === "open" ? "Notification sent · deduplication active" : tab === "acknowledged" ? "Acknowledged — removed from daily digest" : "Recovery notification sent"}
              </span>
            </div>
            <div className="flex gap-2">
              <span className="text-muted w-32 shrink-0">Artifacts</span>
              <a href="#" className="text-accent hover:underline font-mono">View run log →</a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
