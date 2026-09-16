import type { ReactNode } from "react";
import RouteLink from "@/components/RouteLink";
import { NAV_ROUTES, type MatchedRoute, isSameRoute } from "@/router/routes";
import { useRoute } from "@/router/useRoute";
import { formatUtc, relativeTime } from "@/model/time";
import Overview from "@/pages/Overview";
import Workflows from "@/pages/Workflows";
import WorkflowDetail from "@/pages/WorkflowDetail";
import RunDetail from "@/pages/RunDetail";
import Incidents from "@/pages/Incidents";
import Usage from "@/pages/Usage";
import Activity from "@/pages/Activity";
import { useRefresh } from "./RefreshContext";
import { type HealthStatus, useHealth } from "./useHealth";

const TITLES: Record<MatchedRoute["name"], string> = {
  overview: "Overview",
  workflows: "Workflow Portfolio",
  workflow: "Workflow Detail",
  run: "Run Detail",
  incidents: "Incidents",
  usage: "Usage",
  activity: "Activity",
};

const HEALTH_DOT: Record<HealthStatus, string> = {
  ok: "bg-green",
  degraded: "bg-amber",
  unreachable: "bg-red",
  checking: "bg-gray",
};

const isNavActive = (route: MatchedRoute, nav: MatchedRoute["name"]): boolean =>
  route.name === nav || (nav === "workflows" && (route.name === "workflow" || route.name === "run"));

const page = (route: MatchedRoute): ReactNode => {
  switch (route.name) {
    case "overview":
      return <Overview />;
    case "workflows":
      return <Workflows />;
    case "workflow":
      return <WorkflowDetail workflowId={route.id} />;
    case "run":
      return <RunDetail runId={route.id} />;
    case "incidents":
      return <Incidents />;
    case "usage":
      return <Usage />;
    case "activity":
      return <Activity />;
  }
};

export default function App() {
  const route = useRoute();
  const { autoRefresh, setAutoRefresh, refreshNow, generatedAt } = useRefresh();
  const health = useHealth();

  return (
    <div className="flex h-full bg-bg text-text overflow-hidden">
      <aside className="w-52 shrink-0 bg-surface border-r border-border flex flex-col">
        <div className="px-4 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-accent-dim border border-accent/30 flex items-center justify-center text-accent text-xs font-bold">P</div>
            <div>
              <div className="text-xs font-semibold text-text tracking-wide">PRAETORIUM</div>
              <div className="text-[10px] text-muted">Control Room</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-2 py-3 space-y-0.5" aria-label="Main navigation">
          {NAV_ROUTES.map(({ route: target, label }) => {
            const active = isNavActive(route, target.name);
            return (
              <RouteLink
                key={target.name}
                to={target}
                aria-current={isSameRoute(route, target) ? "page" : undefined}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors ${active ? "bg-accent-dim text-accent" : "text-text-2 hover:bg-surface-3 hover:text-text"}`}
              >
                {label}
              </RouteLink>
            );
          })}
        </nav>

        <div className="px-3 py-3 border-t border-border" data-testid="box-health">
          <div className="flex items-center gap-2 mb-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${HEALTH_DOT[health.status]}`} />
            <span className="text-xs text-text-2 font-medium">Praetorium box</span>
          </div>
          <div className="text-[10px] text-muted font-mono space-y-0.5">
            <div>
              /api/v1/health · <span data-testid="health-status">{health.status}</span>
            </div>
            {Object.entries(health.sources).map(([k, v]) => (
              <div key={k}>
                {k} · {v}
              </div>
            ))}
            <div className="text-accent/70">Tailscale only · no-store</div>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-12 border-b border-border bg-surface flex items-center px-5 gap-4 shrink-0">
          <h1 className="text-sm font-semibold text-text whitespace-nowrap">{TITLES[route.name]}</h1>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted font-mono">
            <span title={formatUtc(generatedAt) ?? undefined} data-testid="generated-at">
              {generatedAt ? `Generated ${relativeTime(generatedAt)}` : "No data yet"}
            </span>
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-accent" />
              Auto-refresh 60s
            </label>
            <button onClick={refreshNow} className="px-2.5 py-1 border border-border rounded text-text-2 hover:bg-surface-3 transition-colors">
              Refresh
            </button>
          </div>
        </header>

        {route.unknown && (
          <div className="mx-6 mt-4 bg-amber-dim border border-amber/30 rounded-md px-4 py-2 text-xs text-amber" role="status" data-testid="unknown-route">
            {window.location.pathname} is not a Control Room view — showing Overview.
          </div>
        )}

        <main className="flex-1 overflow-y-auto">{page(route)}</main>
      </div>
    </div>
  );
}
