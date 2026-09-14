import { MARCUS_TRAJAN_TIMELINE } from "../data";

const ACTIVITY_LOG = [
  { time: "15:12", type: "run", actor: "Trajan", event: "Sync #217 started", runId: "run-aws-20260910-1512", status: "running" },
  { time: "14:08", type: "incident", actor: "System", event: "Incident inc-002 raised: Augustus Content board transition missing", runId: "run-ac-20260910-1100", status: "open" },
  { time: "14:01", type: "run", actor: "Trajan", event: "Sync #216 completed successfully", runId: "run-aws-20260910-1400", status: "success" },
  { time: "11:22", type: "incident", actor: "System", event: "Incident inc-001 raised: Standing Research run incomplete", runId: "run-sr-20260910-0901", status: "open" },
  { time: "11:12", type: "run", actor: "Augustus", event: "Augustus Content #88 completed — board transition failed", runId: "run-ac-20260910-1100", status: "incomplete" },
  { time: "11:00", type: "run", actor: "Augustus", event: "Augustus Content run started", runId: "run-ac-20260910-1100", status: "running" },
  { time: "09:14", type: "run", actor: "Claudius", event: "Standing Research run ended incomplete", runId: "run-sr-20260910-0901", status: "incomplete" },
  { time: "09:10", type: "handoff", actor: "Marcus → Trajan", event: "Handoff closed · infrastructure diagnosis complete", runId: "run-aws-20260910-0902", status: "success" },
  { time: "09:02", type: "handoff", actor: "Marcus → Trajan", event: "Handoff opened · infrastructure diagnosis requested", runId: "run-aws-20260910-0902", status: "info" },
  { time: "09:01", type: "run", actor: "Claudius", event: "Standing Research run started", runId: "run-sr-20260910-0901", status: "running" },
  { time: "07:04", type: "run", actor: "Marcus", event: "Daily Plan completed · output created", runId: "run-dp-20260910-0702", status: "success" },
  { time: "07:02", type: "run", actor: "Marcus", event: "Daily Plan run started", runId: "run-dp-20260910-0702", status: "running" },
];

const TYPE_ICON: Record<string, string> = {
  run: "▷", incident: "!", handoff: "⇄", output: "✎", system: "⬡",
};

const STATUS_STYLE: Record<string, string> = {
  success: "text-green", incomplete: "text-amber", failed: "text-red",
  running: "text-blue", open: "text-amber", info: "text-text-2",
};

export default function Activity() {
  return (
    <div className="p-6 max-w-[900px] mx-auto">
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-semibold text-text">Activity log · Sep 10 2026</h2>
        <span className="text-xs text-muted font-mono">Demo data</span>
      </div>

      {/* Timeline */}
      <div className="bg-surface border border-border rounded-md overflow-hidden">
        <div className="border-l-2 border-border ml-8 mr-0">
          {ACTIVITY_LOG.map((ev, i) => (
            <div key={i} className="relative flex items-start gap-4 px-4 py-3 border-b border-border last:border-0 hover:bg-surface-3 transition-colors">
              <div className="absolute left-[-9px] w-3 h-3 rounded-full bg-surface border-2 border-border mt-1" />
              <span className="text-xs font-mono text-muted w-10 shrink-0 mt-0.5">{ev.time}</span>
              <div className={`w-5 h-5 rounded shrink-0 flex items-center justify-center text-xs font-medium mt-0.5 ${
                ev.type === "incident" ? "bg-amber-dim text-amber" :
                ev.type === "handoff" ? "bg-accent-dim text-accent" :
                "bg-surface-3 text-text-2"
              }`}>
                {TYPE_ICON[ev.type] ?? "·"}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-text-2">{ev.actor}</span>
                  <span className={`text-xs ${STATUS_STYLE[ev.status] ?? "text-text-2"}`}>·</span>
                  <span className="text-sm text-text">{ev.event}</span>
                </div>
                <span className="text-xs font-mono text-muted">{ev.runId}</span>
              </div>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded capitalize shrink-0 ${
                ev.status === "success" ? "bg-green-dim text-green" :
                ev.status === "incomplete" ? "bg-amber-dim text-amber" :
                ev.status === "failed" ? "bg-red-dim text-red" :
                ev.status === "running" ? "bg-blue-dim text-blue" :
                ev.status === "open" ? "bg-amber-dim text-amber" :
                "bg-surface-3 text-text-2"
              }`}>
                {ev.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Marcus-Trajan handoff detail */}
      <div className="mt-6">
        <h2 className="text-sm font-semibold text-text mb-3">Agent handoff detail · Marcus → Trajan · Sep 10</h2>
        <div className="bg-surface border border-border rounded-md p-4">
          <div className="grid grid-cols-3 gap-3 mb-4 text-xs">
            <div><span className="text-muted block">Parent run</span><span className="font-mono text-text-2">run-dp-20260910-0702</span></div>
            <div><span className="text-muted block">Child run</span><span className="font-mono text-text-2">run-aws-20260910-0902</span></div>
            <div><span className="text-muted block">Duration</span><span className="font-mono text-text-2">8m 22s</span></div>
          </div>
          <div className="border-l-2 border-border ml-2">
            {MARCUS_TRAJAN_TIMELINE.map((ev, i) => (
              <div key={i} className="relative flex items-start gap-3 pl-5 pb-3 last:pb-0">
                <div className={`absolute left-[-5px] w-2 h-2 rounded-full border-2 mt-1 ${
                  ev.type === "complete" ? "bg-green border-green" :
                  ev.type === "handoff" ? "bg-accent border-accent" :
                  ev.type === "artifact" ? "bg-amber border-amber" :
                  "bg-surface-3 border-border"
                }`} />
                <span className="text-xs font-mono text-muted w-9 shrink-0 mt-0.5">{ev.time}</span>
                <div>
                  <span className={`text-xs font-medium mr-1.5 ${
                    ev.actor === "Marcus" ? "text-blue" : "text-green"
                  }`}>{ev.actor}</span>
                  <span className="text-xs text-text-2">{ev.event}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
