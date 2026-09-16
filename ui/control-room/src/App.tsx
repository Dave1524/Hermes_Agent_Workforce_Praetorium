import { useState } from "react";
import Overview from "./pages/Overview";
import Workflows from "./pages/Workflows";
import WorkflowDetail from "./pages/WorkflowDetail";
import Incidents from "./pages/Incidents";
import Usage from "./pages/Usage";
import Activity from "./pages/Activity";
import { INCIDENTS } from "./data";

type Page = "overview" | "workflows" | "workflow-detail" | "incidents" | "usage" | "activity";

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "⬡" },
  { id: "workflows", label: "Workflows", icon: "⇌" },
  { id: "incidents", label: "Incidents", icon: "!" },
  { id: "usage", label: "Usage", icon: "◎" },
  { id: "activity", label: "Activity", icon: "≡" },
];

const PAGE_TITLES: Record<string, string> = {
  overview: "Overview",
  workflows: "Workflow Portfolio",
  "workflow-detail": "Workflow Detail",
  incidents: "Incidents",
  usage: "Usage",
  activity: "Activity",
};

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [workflowId, setWorkflowId] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [lastRefresh, setLastRefresh] = useState("15:12");
  const [refreshing, setRefreshing] = useState(false);

  const openIncidentCount = INCIDENTS.filter((i) => i.status === "open").length;

  const navigate = (p: string, wId?: string) => {
    setPage(p as Page);
    if (wId) setWorkflowId(wId);
  };

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => {
      setRefreshing(false);
      const now = new Date();
      setLastRefresh(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`);
    }, 900);
  };

  return (
    <div className="flex h-full bg-bg text-text overflow-hidden">
      {/* Sidebar */}
      <aside className="w-52 shrink-0 bg-surface border-r border-border flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-accent-dim border border-accent/30 flex items-center justify-center text-accent text-xs font-bold">P</div>
            <div>
              <div className="text-xs font-semibold text-text tracking-wide">PRAETORIUM</div>
              <div className="text-[10px] text-muted">Control Room</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 space-y-0.5" role="navigation" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const active = page === item.id || (item.id === "workflows" && page === "workflow-detail");
            return (
              <button
                key={item.id}
                onClick={() => { setPage(item.id); setWorkflowId(undefined); }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors text-left ${
                  active
                    ? "bg-accent-dim text-accent"
                    : "text-text-2 hover:bg-surface-3 hover:text-text"
                }`}
              >
                <span className="text-xs w-4 text-center" aria-hidden>{item.icon}</span>
                <span>{item.label}</span>
                {item.id === "incidents" && openIncidentCount > 0 && (
                  <span className="ml-auto text-[10px] font-mono bg-red text-white rounded-full px-1.5 py-0.5 leading-none">{openIncidentCount}</span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Box status */}
        <div className="px-3 py-3 border-t border-border">
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green animate-pulse" />
            <span className="text-xs text-text-2 font-medium">Praetorium box</span>
          </div>
          <div className="text-[10px] text-muted font-mono space-y-0.5">
            <div>Connected · healthy</div>
            <div>Refreshed {lastRefresh}</div>
            <div className="text-accent/70">Private · Local</div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="h-12 border-b border-border bg-surface flex items-center px-5 gap-4 shrink-0">
          <h1 className="text-sm font-semibold text-text whitespace-nowrap">{PAGE_TITLES[page] ?? "Praetorium"}</h1>
          <div className="flex-1 max-w-xs ml-4">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search workflows…"
              className="w-full bg-surface-2 border border-border rounded px-3 py-1 text-xs text-text placeholder:text-muted focus:outline-none focus:border-border-2"
            />
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted font-mono">
            <span>{refreshing ? "Refreshing…" : `Last refresh ${lastRefresh}`}</span>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="px-2.5 py-1 border border-border rounded text-text-2 hover:bg-surface-3 transition-colors disabled:opacity-50"
            >
              {refreshing ? "↻" : "Refresh"}
            </button>
          </div>
          <div className="text-[10px] text-muted border border-border/50 rounded px-1.5 py-0.5">DEMO</div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          {page === "overview" && <Overview onNavigate={navigate} />}
          {page === "workflows" && <Workflows onNavigate={navigate} />}
          {page === "workflow-detail" && workflowId && (
            <WorkflowDetail workflowId={workflowId} onBack={() => setPage("workflows")} />
          )}
          {page === "workflow-detail" && !workflowId && <Workflows onNavigate={navigate} />}
          {page === "incidents" && <Incidents onNavigate={navigate} />}
          {page === "usage" && <Usage />}
          {page === "activity" && <Activity />}
        </main>
      </div>
    </div>
  );
}
