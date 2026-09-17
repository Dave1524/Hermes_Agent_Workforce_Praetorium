import { runDetailResponseSchema } from "@/api/schemas/run";
import ArtifactLink from "@/components/ArtifactLink";
import DataStatusStrip from "@/components/DataStatusStrip";
import { CostCell, UsageCell } from "@/components/MeasurementCell";
import ClosedChip from "@/components/ClosedChip";
import OutcomeBadge from "@/components/OutcomeBadge";
import { Panel, Row } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { toRun } from "@/model/run";
import { formatDuration, formatUtc } from "@/model/time";
import { usePageResource } from "@/shell/usePageResource";

const ASSERTION_TONE: Record<string, string> = { pass: "text-green", fail: "text-red", skip: "text-muted" };

export default function RunDetail({ runId }: { runId: string }) {
  const resource = usePageResource(`/api/v1/runs/${encodeURIComponent(runId)}`, runDetailResponseSchema);
  if (resource.status === "error" && resource.error) return <ErrorNotice what={`run ${runId}`} error={resource.error} onRetry={resource.refresh} />;
  if (!resource.data) return <Loading what={`run ${runId}`} />;
  const run = toRun(resource.data.items);

  return (
    <>
      <DataStatusStrip status={resource.data.dataStatus} />
      <div className="p-6 max-w-[1000px] mx-auto">
        {run.workflowId ? (
          <RouteLink to={{ name: "workflow", id: run.workflowId }} className="inline-flex items-center gap-1.5 text-sm text-text-2 hover:text-text mb-5 transition-colors">
            <span aria-hidden>←</span> {run.workflowId}
          </RouteLink>
        ) : (
          <RouteLink to={{ name: "workflows" }} className="inline-flex items-center gap-1.5 text-sm text-text-2 hover:text-text mb-5 transition-colors">
            <span aria-hidden>←</span> Workflows
          </RouteLink>
        )}

        <header className="bg-surface border border-border rounded-md p-5 mb-5">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-lg font-semibold text-text font-mono">{run.id || runId}</h2>
            <OutcomeBadge outcome={run.outcome} />
            <ClosedChip closed={run.closed} />
            {run.agent && <span className="text-xs text-text-2">{run.agent}</span>}
            {run.model && <span className="text-xs font-mono text-muted">{run.model}</span>}
          </div>
          {run.reason && <p className="text-sm text-text-2 mt-2">{run.reason}</p>}
          {run.closed && (
            <p className="text-sm text-text-2 mt-2" data-testid="closed">
              Closed {formatUtc(run.closed.at) ?? run.closed.at} by {run.closed.by} — {run.closed.reason}
            </p>
          )}
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Panel title="Timing">
            <Row label="Started">{formatUtc(run.startedAt) ?? "—"}</Row>
            <Row label="Ended">{formatUtc(run.endedAt) ?? "—"}</Row>
            <Row label="Duration">{formatDuration(run.durationSeconds) ?? "—"}</Row>
            <Row label="Ended"><When iso={run.endedAt} /></Row>
            <Row label="Unit">{run.unit ?? "—"}</Row>
          </Panel>

          <Panel title="Usage & cost">
            <Row label="Tokens"><UsageCell usage={run.usage} /></Row>
            {run.usage.status === "measured" && (
              <>
                <Row label="Input">{run.usage.value.input}</Row>
                <Row label="Output">{run.usage.value.output}</Row>
                <Row label="Cache">{run.usage.value.cache}</Row>
              </>
            )}
            <Row label="Cost"><CostCell cost={run.cost} /></Row>
          </Panel>

          <Panel title="Artifact">
            <Row label="Artifact"><ArtifactLink artifact={run.artifact} /></Row>
            <Row label="Kind">{run.artifact?.kind ?? "—"}</Row>
            <Row label="URI">{run.artifact?.uri ?? "—"}</Row>
            {run.nextAction && (
              <>
                <Row label="Next actor">{run.nextAction.actor ?? "—"}</Row>
                <Row label="Next action">{run.nextAction.action ?? "—"}</Row>
                <Row label="Due"><When iso={run.nextAction.dueAt} /></Row>
              </>
            )}
          </Panel>

          <Panel title="Assertions">
            {run.assertions.length === 0 && <p className="text-xs text-muted">No assertions recorded.</p>}
            <ul className="space-y-1.5" data-testid="assertions">
              {run.assertions.map((a) => (
                <li key={a.id} className="text-xs flex gap-2">
                  <span className={`font-mono w-10 shrink-0 ${ASSERTION_TONE[a.status] ?? "text-text-2"}`}>{a.status}</span>
                  <span className="font-mono text-text">{a.id}</span>
                  {a.message && <span className="text-text-2">— {a.message}</span>}
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Receipt">
            <Row label="Receipt">{run.receiptPath ?? "—"}</Row>
          </Panel>

          <Panel title="Agent handoff">
            {run.parentRunId === null && run.handoff === null ? (
              <p className="text-xs text-muted" data-testid="handoff">Unknown — no handoff telemetry (T5.3d).</p>
            ) : (
              <div data-testid="handoff">
                <Row label="Parent run">{run.parentRunId ? <RouteLink to={{ name: "run", id: run.parentRunId }} className="text-accent hover:underline">{run.parentRunId}</RouteLink> : "—"}</Row>
                {run.handoff !== null && <pre className="mt-2 text-[11px] font-mono text-text-2 bg-surface-2 border border-border rounded p-3 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(run.handoff, null, 2)}</pre>}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
