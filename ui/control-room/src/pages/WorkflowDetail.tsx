import { useState } from "react";
import { getText } from "@/api/client";
import { runListResponseSchema } from "@/api/schemas/run";
import { workflowDetailResponseSchema } from "@/api/schemas/workflow";
import AgentAvatar from "@/components/AgentAvatar";
import ArtifactLink from "@/components/ArtifactLink";
import ControlStateBadge from "@/components/ControlStateBadge";
import DataStatusStrip from "@/components/DataStatusStrip";
import HealthBadge from "@/components/HealthBadge";
import { CostCell, NotMeasured, UsageCell } from "@/components/MeasurementCell";
import OutcomeBadge from "@/components/OutcomeBadge";
import { Panel, Row } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import type { Benefit } from "@/model/benefit";
import { toRun } from "@/model/run";
import { formatCadence, formatDuration, formatUtc } from "@/model/time";
import { formatCost, formatUsage } from "@/model/tokens";
import { type TriggerView, type WorkflowDetail as Detail, toWorkflowDetail } from "@/model/workflowDetail";
import { usePageResource, useSecondaryResource } from "@/shell/usePageResource";

const pct = (rate: number | null): string => (rate === null ? "—" : `${Math.round(rate * 100)}%`);

export default function WorkflowDetail({ workflowId }: { workflowId: string }) {
  const encoded = encodeURIComponent(workflowId);
  const workflow = usePageResource(`/api/v1/workflows/${encoded}`, workflowDetailResponseSchema);
  const runs = useSecondaryResource(`/api/v1/workflows/${encoded}/runs`, runListResponseSchema);

  if (workflow.status === "error" && workflow.error) return <ErrorNotice what={`workflow ${workflowId}`} error={workflow.error} onRetry={workflow.refresh} />;
  if (!workflow.data) return <Loading what={`workflow ${workflowId}`} />;
  const d = toWorkflowDetail(workflow.data.items);
  const { row } = d;

  return (
    <>
      <DataStatusStrip status={workflow.data.dataStatus} />
      <div className="p-6 max-w-[1100px] mx-auto">
        <RouteLink to={{ name: "workflows" }} className="inline-flex items-center gap-1.5 text-sm text-text-2 hover:text-text mb-5 transition-colors">
          <span aria-hidden>←</span> Workflows
        </RouteLink>

        <header className="bg-surface border border-border rounded-md p-5 mb-5">
          <div className="flex items-start gap-4">
            <AgentAvatar name={row.owner} size="md" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="text-lg font-semibold text-text">{row.name}</h2>
                <HealthBadge health={row.health} size="md" />
                <ControlStateBadge state={row.controlState} />
                <span className="font-mono text-xs text-muted">{row.id}</span>
              </div>
              {d.purpose && <p className="text-text-2 text-sm mt-1.5 max-w-xl">{d.purpose}</p>}
              <ContractSentence detail={d} />
            </div>
          </div>
        </header>

        <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
          <Card label="Last run"><When iso={row.lastRunAt} /></Card>
          <Card label="Next run"><When iso={row.nextRunAt} estimated={row.nextRunEstimated} /></Card>
          <Card label="Valid / eligible">{d.benefit ? `${Math.round((d.benefit.validArtifactRate ?? 0) * (d.benefit.eligibleRuns ?? 0))} / ${d.benefit.eligibleRuns ?? "—"}` : "—"}</Card>
          <Card label="Valid artifact rate">{pct(d.benefit?.validArtifactRate ?? null)}</Card>
          <Card label="Tokens (last run)">{formatUsage(row.usage)}</Card>
          <Card label="Cost (last run)">{formatCost(row.cost)}</Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Panel title="Triggers & schedules">
            {d.triggers.length === 0 && <p className="text-xs text-muted">No triggers wired to this workflow.</p>}
            <div className="space-y-2">
              {d.triggers.map((t, i) => <TriggerCard key={t.unit} index={i + 1} trigger={t} />)}
            </div>
            <div className="mt-3 text-xs text-muted font-mono">
              control source {d.controlSource ?? "—"} · last trigger {formatUtc(d.lastTriggerAt) ?? "—"}
            </div>
          </Panel>

          <Panel title="Latest output">
            <Row label="Artifact"><ArtifactLink artifact={d.lastRun?.artifact ?? null} /></Row>
            <Row label="Outcome">{d.lastRun ? <OutcomeBadge outcome={d.lastRun.outcome} /> : "—"}</Row>
            <Row label="Ended"><When iso={d.lastRun?.endedAt} /></Row>
            <Row label="Run">{d.lastRun?.id ? <RouteLink to={{ name: "run", id: d.lastRun.id }} className="text-accent hover:underline">{d.lastRun.id}</RouteLink> : "—"}</Row>
            <Row label="Last valid artifact"><When iso={d.lastValidArtifactAt} /></Row>
            <Row label="Freshness">{row.artifactFreshness ?? "—"}</Row>
            {d.lastRun?.reason && <p className="text-xs text-text-2 mt-2">{d.lastRun.reason}</p>}
          </Panel>

          <Panel title="Recent runs">
            {runs.status === "error" && runs.error && <ErrorNotice what="the runs" error={runs.error} onRetry={runs.refresh} />}
            {!runs.data && runs.status !== "error" && <Loading what="runs" />}
            {runs.data && <RunsTable runs={runs.data.items.map(toRun)} />}
          </Panel>

          <Panel title="Benefit evidence">
            <BenefitPanel benefit={d.benefit} />
          </Panel>

          <Panel title="Lineage">
            <p className="text-xs text-muted mb-2">Each stage names where its value came from; a stage with nothing behind it is Unknown, never a guess.</p>
            <ol className="space-y-1" data-testid="lineage">
              {d.lineage.map((s, i) => (
                <li key={s.stage} className="flex gap-3 text-xs py-1 border-b border-border last:border-0">
                  <span className="font-mono text-muted w-24 shrink-0">{i + 1}. {s.stage.replace("_", " ")}</span>
                  <span className="flex-1 min-w-0 text-text-2 break-words">
                    {s.value.length === 0 ? <span className="text-muted">Unknown</span> : s.value.map((v) => <span key={v} className="block">{v}</span>)}
                  </span>
                  <span className="font-mono text-muted shrink-0">{s.source ?? ""}</span>
                </li>
              ))}
            </ol>
          </Panel>

          <Panel title="Contract & links">
            <Row label="Contract">{d.contractStatus ?? "—"}{d.contractError && <span className="text-red"> · {d.contractError}</span>}</Row>
            <Row label="Local">{d.links?.contractLocal ?? "—"}</Row>
            <Row label="GitHub">{d.links?.contractGithub ? <a href={d.links.contractGithub} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">open</a> : "—"}</Row>
            <Row label="Dev plan">{d.links?.devPlanDoc ? <a href={d.links.devPlanDoc} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">{d.links.devPlanTracker ?? "doc"}</a> : (d.links?.devPlanTracker ?? "—")}</Row>
            <Row label="Tasks">{d.links?.taskIds.length ? d.links.taskIds.join(", ") : "—"}</Row>
            <Row label="Manifests">{d.manifestPaths.length ? d.manifestPaths.join(", ") : "—"}</Row>
            {d.contract && <ContractText workflowId={row.id} />}
          </Panel>
        </div>

        {d.incompleteRuns.length > 0 && (
          <div className="mt-5">
            <Panel title="Incomplete runs">
              <RunsTable runs={d.incompleteRuns} />
            </Panel>
          </div>
        )}
      </div>
    </>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface border border-border rounded-md px-3 py-3">
      <div className="text-base font-semibold font-mono text-text">{children}</div>
      <div className="text-xs text-muted mt-0.5">{label}</div>
    </div>
  );
}

function ContractSentence({ detail }: { detail: Detail }) {
  const c = detail.contract;
  if (!c) return null;
  return (
    <p className="text-muted text-xs mt-2 italic" data-testid="contract-sentence">
      When <span className="not-italic text-text-2">{c.trigger ?? "its trigger"}</span> occurs, this workflow produces{" "}
      <span className="not-italic text-text-2">{c.artifact ?? "an artifact"}</span> for <span className="not-italic text-text-2">{c.beneficiary ?? "its beneficiary"}</span>
      {c.next_actor && c.next_action && (
        <>
          , so <span className="not-italic text-text-2">{c.next_actor}</span> can <span className="not-italic text-text-2">{c.next_action}</span>
        </>
      )}
      .
    </p>
  );
}

function TriggerCard({ index, trigger }: { index: number; trigger: TriggerView }) {
  return (
    <div className="bg-surface-2 border border-border rounded p-3 text-xs" data-testid="trigger">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-accent font-mono">Trigger {index}</span>
        <span className="font-mono text-text-2">{trigger.unit}</span>
        {trigger.kind && <span className="text-muted">· {trigger.kind}</span>}
      </div>
      <Row label="Timer">{trigger.timerState ?? "—"}{trigger.enabledState && <span className="text-muted"> · {trigger.enabledState}</span>}</Row>
      <Row label="Schedule">{trigger.spec ?? "—"}{trigger.cadenceSeconds !== null && <span className="text-muted"> · {formatCadence(trigger.cadenceSeconds)}</span>}</Row>
      <Row label="Last trigger"><When iso={trigger.lastTriggerAt} /></Row>
      <Row label="Next run"><When iso={trigger.nextRunAt} /></Row>
      <Row label="Persistent">{trigger.persistent === null ? "—" : trigger.persistent ? "yes" : "no"}</Row>
      {trigger.errors.length > 0 && <p className="text-red mt-1 font-mono">{trigger.errors.join("; ")}</p>}
    </div>
  );
}

function RunsTable({ runs }: { runs: ReturnType<typeof toRun>[] }) {
  if (runs.length === 0) return <p className="text-xs text-muted">No runs recorded.</p>;
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted border-b border-border">
          <th className="text-left py-1.5 font-medium">Run</th>
          <th className="text-left py-1.5 font-medium">Outcome</th>
          <th className="text-left py-1.5 font-medium">Ended</th>
          <th className="text-left py-1.5 font-medium">Duration</th>
          <th className="text-right py-1.5 font-medium">Tokens</th>
          <th className="text-right py-1.5 font-medium">Cost</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {runs.map((run) => (
          <tr key={run.id} className="hover:bg-surface-3 transition-colors">
            <td className="py-2 font-mono">{run.id ? <RouteLink to={{ name: "run", id: run.id }} className="text-accent hover:underline">{run.id}</RouteLink> : "—"}</td>
            <td className="py-2"><OutcomeBadge outcome={run.outcome} /></td>
            <td className="py-2"><When iso={run.endedAt} /></td>
            <td className="py-2 font-mono text-muted">{formatDuration(run.durationSeconds) ?? "—"}</td>
            <td className="py-2 text-right"><UsageCell usage={run.usage} /></td>
            <td className="py-2 text-right"><CostCell cost={run.cost} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const DECISION_STYLE: Record<Benefit["decision"], string> = {
  Keep: "text-green bg-green-dim",
  Improve: "text-amber bg-amber-dim",
  Retire: "text-red bg-red-dim",
  Unknown: "text-muted bg-surface-3",
};

function BenefitPanel({ benefit }: { benefit: Benefit | null }) {
  if (!benefit) return <p className="text-xs text-muted">No benefit ledger entry for this workflow.</p>;
  const signals = benefit.consumption.status === "measured" ? benefit.consumption.value : null;
  const denominator = signals?.artifactRuns ?? 0;
  const bars: Array<[string, number]> = signals ? [["Opened", signals.opened], ["Approved", signals.approved], ["Sent", signals.sent], ["Marked useful", signals.markedUseful]] : [];
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-2">
        <span className={`font-mono px-2 py-0.5 rounded text-[11px] ${DECISION_STYLE[benefit.decision]}`} data-decision={benefit.decision}>{benefit.decision}</span>
        {benefit.decidedBy && <span className="text-xs text-muted">by {benefit.decidedBy} · {formatUtc(benefit.decidedAt) ?? "—"}</span>}
      </div>
      <Row label="Eligible runs">{benefit.eligibleRuns ?? "—"}</Row>
      <Row label="Valid artifact rate">{pct(benefit.validArtifactRate)}</Row>
      <Row label="Latency">{formatDuration(benefit.latencySeconds) ?? "—"}</Row>
      <Row label="Manual minutes avoided">{benefit.manualMinutesAvoided ?? "—"}</Row>
      <p className="text-xs text-muted pt-2">Consumption signals, measured independently and never combined into a score.</p>
      {signals === null ? (
        <NotMeasured status={benefit.consumption.status === "unknown" ? "unknown" : "unavailable"} />
      ) : (
        bars.map(([label, n]) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-xs text-text-2 w-28 shrink-0">{label}</span>
            <meter className="flex-1 h-1.5" min={0} max={Math.max(denominator, 1)} value={n} aria-label={label} />
            <span className="text-xs font-mono text-muted w-14 text-right">{n} of {denominator}</span>
          </div>
        ))
      )}
    </div>
  );
}

function ContractText({ workflowId }: { workflowId: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    getText(`/api/v1/workflows/${encodeURIComponent(workflowId)}/contract`)
      .then(setText)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };
  return (
    <details className="mt-3" onToggle={(e) => e.currentTarget.open && text === null && load()}>
      <summary className="text-xs text-accent cursor-pointer">Contract text</summary>
      {error && <p className="text-xs text-red mt-2 font-mono">{error}</p>}
      {text !== null && <pre className="mt-2 text-[11px] font-mono text-text-2 bg-surface-2 border border-border rounded p-3 overflow-x-auto whitespace-pre-wrap">{text}</pre>}
    </details>
  );
}
