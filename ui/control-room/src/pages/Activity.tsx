import { activityResponseSchema } from "@/api/schemas/activity";
import DataStatusStrip from "@/components/DataStatusStrip";
import { Empty } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { formatUtc } from "@/model/time";
import { usePageResource } from "@/shell/usePageResource";

const TYPE_ICON: Record<string, string> = { run: "▷", incident: "!", handoff: "⇄", output: "✎", control: "⚙", proposal: "⎇" };
const TYPE_TONE: Record<string, string> = { incident: "bg-amber-dim text-amber", handoff: "bg-accent-dim text-accent", control: "bg-blue-dim text-blue", proposal: "bg-accent-dim text-accent" };
const STATUS_TONE: Record<string, string> = { artifact: "text-green", decline: "text-text-2", failed: "text-red", skipped: "text-muted", running: "text-blue", open: "text-amber", resolved: "text-green" };

export default function Activity() {
  const resource = usePageResource("/api/v1/activity", activityResponseSchema);
  if (resource.status === "error" && resource.error) return <ErrorNotice what="the activity log" error={resource.error} onRetry={resource.refresh} />;
  if (!resource.data) return <Loading what="the activity log" />;
  const items = resource.data.items;

  return (
    <>
      <DataStatusStrip status={resource.data.dataStatus} />
      <div className="p-6 max-w-[900px] mx-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-text">Activity log</h2>
          <span className="text-xs text-muted font-mono">{items.length} events · generated {formatUtc(resource.data.generatedAt)}</span>
        </div>
        {items.length === 0 && <Empty>No activity recorded.</Empty>}
        {items.length > 0 && (
          <ol className="bg-surface border border-border rounded-md overflow-hidden">
            {items.map((ev) => (
              <li key={ev.id} className="flex items-start gap-4 px-4 py-3 border-b border-border last:border-0 hover:bg-surface-3 transition-colors" data-testid="activity-row">
                <span className="w-16 shrink-0 mt-0.5"><When iso={ev.time} /></span>
                <div className={`w-5 h-5 rounded shrink-0 flex items-center justify-center text-xs font-medium mt-0.5 ${TYPE_TONE[ev.type ?? ""] ?? "bg-surface-3 text-text-2"}`} aria-label={ev.type ?? "event"}>
                  {TYPE_ICON[ev.type ?? ""] ?? "·"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {ev.actor && <span className="text-xs text-text-2">{ev.actor}</span>}
                    <span className="text-sm text-text">{ev.event ?? "—"}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[11px] font-mono">
                    {ev.runId && <RouteLink to={{ name: "run", id: ev.runId }} className="text-accent hover:underline">{ev.runId}</RouteLink>}
                    {ev.status && <span className={STATUS_TONE[ev.status] ?? "text-text-2"}>{ev.status}</span>}
                    <span className="text-muted">{formatUtc(ev.time) ?? ""}</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </>
  );
}
