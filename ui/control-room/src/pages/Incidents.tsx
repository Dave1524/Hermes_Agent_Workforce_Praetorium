import { useState } from "react";
import { incidentsResponseSchema } from "@/api/schemas/incidents";
import DataStatusStrip from "@/components/DataStatusStrip";
import { Empty } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { type IncidentView, type Severity, toIncident } from "@/model/incident";
import { usePageResource } from "@/shell/usePageResource";

const TABS = ["open", "resolved"] as const;
type Tab = (typeof TABS)[number];

const SEVERITY_DOT: Record<Severity, string> = { critical: "bg-red", high: "bg-red", medium: "bg-amber", low: "bg-blue", unknown: "bg-gray" };

const inTab = (incident: IncidentView, tab: Tab): boolean => (tab === "resolved" ? incident.status === "resolved" : incident.status !== "resolved");

export default function Incidents() {
  const resource = usePageResource("/api/v1/incidents", incidentsResponseSchema);
  const [tab, setTab] = useState<Tab>("open");
  if (resource.status === "error" && resource.error) return <ErrorNotice what="the incidents" error={resource.error} onRetry={resource.refresh} />;
  if (!resource.data) return <Loading what="the incidents" />;
  const incidents = resource.data.items.map(toIncident);
  const counts = { open: incidents.filter((i) => inTab(i, "open")).length, resolved: incidents.filter((i) => inTab(i, "resolved")).length };
  const shown = incidents.filter((i) => inTab(i, tab));

  return (
    <>
      <DataStatusStrip status={resource.data.dataStatus} />
      <div className="p-6 max-w-[1000px] mx-auto">
        <div className="flex gap-0 border-b border-border mb-5" role="tablist">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-sm capitalize border-b-2 -mb-px transition-colors ${tab === t ? "border-accent text-accent" : "border-transparent text-text-2 hover:text-text"}`}
            >
              {t}
              <span className={`ml-2 text-[10px] font-mono rounded-full px-1.5 py-0.5 ${t === "open" && counts[t] > 0 ? "bg-red text-white" : "bg-surface-3 text-text-2"}`}>{counts[t]}</span>
            </button>
          ))}
        </div>

        <div className="space-y-3">
          {shown.length === 0 && <Empty>No {tab} incidents.</Empty>}
          {shown.map((inc) => <IncidentCard key={inc.id} incident={inc} />)}
        </div>
      </div>
    </>
  );
}

function IncidentCard({ incident }: { incident: IncidentView }) {
  return (
    <article className="bg-surface border border-border rounded-md p-4" data-testid="incident">
      <div className="flex items-start gap-3">
        <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${SEVERITY_DOT[incident.severity]}`} aria-label={`${incident.severity} severity`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted">{incident.id}</span>
            {incident.workflowId && <RouteLink to={{ name: "workflow", id: incident.workflowId }} className="font-medium text-sm text-text hover:text-accent">{incident.workflowId}</RouteLink>}
            {incident.agent && <span className="text-text-2 text-xs">· {incident.agent}</span>}
            {incident.klass && <span className="text-[10px] font-mono text-text-2 bg-surface-3 rounded px-1.5">{incident.klass}</span>}
            <span className="text-[10px] font-mono text-muted ml-auto">{incident.status}</span>
          </div>
          {incident.issue && <p className="text-sm text-text-2 mt-1">{incident.issue}</p>}
          {incident.failedAssertion && <p className="text-xs font-mono text-red mt-1">{incident.failedAssertion}</p>}
          <div className="flex items-center gap-3 mt-2 text-xs flex-wrap text-muted font-mono">
            <span>first <When iso={incident.firstSeen} /></span>
            <span>last <When iso={incident.lastSeen} /></span>
            {incident.observations !== null && <span>{incident.observations}× observed</span>}
            {incident.notifiedAt && <span>notified <When iso={incident.notifiedAt} /></span>}
            {incident.resolvedAt && <span>resolved <When iso={incident.resolvedAt} /></span>}
            {incident.runId && <RouteLink to={{ name: "run", id: incident.runId }} className="text-accent hover:underline">{incident.runId}</RouteLink>}
          </div>
          {incident.requiredAction && <p className="text-xs text-text-2 mt-2">{incident.requiredAction}</p>}
          {incident.evidence.length > 0 && (
            <ul className="mt-2 text-[11px] font-mono text-muted space-y-0.5">
              {incident.evidence.map((e) => <li key={e} className="break-all">{e}</li>)}
            </ul>
          )}
        </div>
      </div>
    </article>
  );
}
