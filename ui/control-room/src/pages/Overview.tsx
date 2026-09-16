import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { exceptionsResponseSchema } from "@/api/schemas/exceptions";
import { type Reliability, overviewResponseSchema } from "@/api/schemas/overview";
import AgentAvatar from "@/components/AgentAvatar";
import DataStatusStrip from "@/components/DataStatusStrip";
import { CostCell, UsageCell } from "@/components/MeasurementCell";
import OutcomeBadge from "@/components/OutcomeBadge";
import { Empty, Panel, SectionHeader, Stat } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import When from "@/components/When";
import { type ExceptionView, exceptionKindLabel, sortExceptions, toException } from "@/model/exception";
import { toRun } from "@/model/run";
import { formatTokens } from "@/model/tokens";
import { toAgentUsage, totalCost } from "@/model/usage";
import { usePageResource, useSecondaryResource } from "@/shell/usePageResource";
import ArtifactLink from "@/components/ArtifactLink";

export default function Overview() {
  const overview = usePageResource("/api/v1/overview", overviewResponseSchema);
  const exceptions = useSecondaryResource("/api/v1/exceptions", exceptionsResponseSchema);

  if (overview.status === "error" && overview.error) return <ErrorNotice what="the overview" error={overview.error} onRetry={overview.refresh} />;
  if (!overview.data) return <Loading what="the overview" />;
  const { summary, reliability7d, recentOutputs, agentUsage, dataStatus } = overview.data;
  const queue = exceptions.data ? sortExceptions(exceptions.data.items.map(toException)) : null;
  const usage = agentUsage.map(toAgentUsage);
  const total = totalCost(usage);

  return (
    <>
      <DataStatusStrip status={dataStatus} />
      <div className="p-6 max-w-[1200px] mx-auto space-y-6">
        <div className="grid grid-cols-5 gap-3">
          <div data-testid="stat-workflows"><Stat label="Workflows" value={summary.workflows ?? "—"} tone="text-text-2" /></div>
          <div data-testid="stat-healthy"><Stat label="Healthy" value={summary.healthy ?? "—"} tone="text-green" /></div>
          <div data-testid="stat-running"><Stat label="Running" value={summary.running ?? "—"} tone="text-blue" /></div>
          <div data-testid="stat-failed"><Stat label="Failed" value={summary.failed ?? "—"} tone="text-red" /></div>
          <div data-testid="stat-paused"><Stat label="Paused" value={summary.paused ?? "—"} tone="text-muted" /></div>
        </div>

        <div className="grid grid-cols-3 gap-5">
          <div className="col-span-2 space-y-3">
            <SectionHeader title="Needs attention" count={queue?.length} countColor="bg-amber text-bg" />
            {exceptions.status === "error" && exceptions.error && <ErrorNotice what="the exceptions queue" error={exceptions.error} onRetry={exceptions.refresh} />}
            {queue === null && exceptions.status !== "error" && <Loading what="the exceptions queue" />}
            {queue?.length === 0 && <Empty><span className="text-green text-lg block mb-2">✓</span>Nothing in the queue.</Empty>}
            {queue?.map((row, i) => <ExceptionCard key={`${row.kind}:${row.workflowId}:${i}`} row={row} />)}
            {exceptions.data && exceptions.data.dataQuality.length > 0 && (
              <Panel title="Data quality">
                <ul className="text-xs text-text-2 space-y-1.5">
                  {exceptions.data.dataQuality.map((d) => (
                    <li key={d.id} className="flex gap-2">
                      <span className="font-mono text-muted shrink-0">{d.workflowId ?? d.agent ?? "—"}</span>
                      <span>{d.issue ?? d.failedAssertion ?? d.id}</span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
          </div>

          <div className="space-y-3">
            <SectionHeader title="7-day reliability" />
            <ReliabilityPanel reliability={reliability7d ?? { status: "unknown", days: [] }} />
            <SectionHeader title="Agent usage" />
            <div className="bg-surface border border-border rounded-md divide-y divide-border">
              {usage.map((a) => (
                <div key={a.agent} className="px-4 py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AgentAvatar name={a.agent} />
                    <span className="text-sm text-text">{a.agent}</span>
                  </div>
                  <div className="text-right space-y-0.5">
                    <div><UsageCell usage={a.usage} /></div>
                    <div><CostCell cost={a.cost} /></div>
                  </div>
                </div>
              ))}
              {usage.length === 0 && <div className="px-4 py-3 text-xs text-muted">No agent usage recorded.</div>}
              <div className="px-4 py-2.5 flex justify-between text-xs font-mono text-text-2 bg-surface-3">
                <span>Total ({total.measured} of {usage.length} measured)</span>
                <span className="text-text">{total.amount === null ? "unavailable" : `${total.amount.toFixed(2)} ${total.currency}`}</span>
              </div>
            </div>
          </div>
        </div>

        <div>
          <SectionHeader title="Recent outputs" />
          <div className="bg-surface border border-border rounded-md mt-3 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted">
                  <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
                  <th className="text-left px-4 py-2.5 font-medium">Output</th>
                  <th className="text-left px-4 py-2.5 font-medium">Ended</th>
                  <th className="text-left px-4 py-2.5 font-medium">Outcome</th>
                  <th className="text-right px-4 py-2.5 font-medium">Run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recentOutputs.map(toRun).map((run) => (
                  <tr key={`${run.workflowId}:${run.id}`} className="hover:bg-surface-3 transition-colors">
                    <td className="px-4 py-3 text-text-2">
                      {run.workflowId ? <RouteLink to={{ name: "workflow", id: run.workflowId }} className="hover:text-text">{run.workflowId}</RouteLink> : "—"}
                    </td>
                    <td className="px-4 py-3 text-text font-medium"><ArtifactLink artifact={run.artifact} /></td>
                    <td className="px-4 py-3"><When iso={run.endedAt} /></td>
                    <td className="px-4 py-3"><OutcomeBadge outcome={run.outcome} /></td>
                    <td className="px-4 py-3 text-right">
                      {run.id ? <RouteLink to={{ name: "run", id: run.id }} className="font-mono text-xs text-accent hover:underline">{run.id}</RouteLink> : "—"}
                    </td>
                  </tr>
                ))}
                {recentOutputs.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-text-2 text-sm">No runs recorded.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

function ExceptionCard({ row }: { row: ExceptionView }) {
  return (
    <div className="bg-surface border border-border rounded-md p-4">
      <div className="flex items-start gap-3">
        <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${row.kind === "failed" ? "bg-red" : "bg-amber"}`} aria-hidden />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted">{exceptionKindLabel(row.kind)}</span>
            {row.workflowId && <RouteLink to={{ name: "workflow", id: row.workflowId }} className="font-medium text-sm text-text hover:text-accent">{row.workflowId}</RouteLink>}
            {row.owner && <span className="text-text-2 text-xs">· {row.owner}</span>}
            {row.paused && <span className="text-[10px] font-mono text-text-2 bg-surface-3 rounded px-1.5">paused</span>}
          </div>
          {row.issue && <p className="text-sm text-text-2 mt-1">{row.issue}</p>}
          <div className="flex items-center gap-3 mt-2 text-xs flex-wrap">
            {row.since && <span className="text-muted font-mono">since <When iso={row.since} /></span>}
            {row.requiredAction && <span className="text-text-2">{row.requiredAction}</span>}
            {row.runId && <RouteLink to={{ name: "run", id: row.runId }} className="font-mono text-accent hover:underline">{row.runId}</RouteLink>}
          </div>
        </div>
      </div>
    </div>
  );
}

function ReliabilityPanel({ reliability }: { reliability: Reliability }) {
  const days = reliability.days.map((d) => ({ ...d, label: d.day.slice(5) }));
  const eligible = days.reduce((s, d) => s + d.eligible, 0);
  const valid = days.reduce((s, d) => s + d.valid, 0);
  return (
    <div className="bg-surface border border-border rounded-md p-4" data-testid="reliability">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-text text-sm font-medium">Valid artifacts / eligible runs</span>
        <span className="text-xs font-mono text-text-2">{reliability.status === "measured" ? `${valid}/${eligible}` : reliability.status}</span>
      </div>
      {reliability.status === "measured" ? (
        <ResponsiveContainer width="100%" height={100}>
          <BarChart data={days} barCategoryGap="30%">
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--color-muted)" }} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              content={({ active, payload }) => {
                const d = payload?.[0]?.payload as { valid: number; eligible: number; day: string } | undefined;
                if (!active || !d) return null;
                return <div className="bg-surface-3 border border-border rounded px-2 py-1.5 text-xs font-mono text-text">{d.day} · {d.valid}/{d.eligible} valid</div>;
              }}
            />
            <Bar dataKey="eligible" fill="var(--color-border)" radius={[2, 2, 0, 0]} />
            <Bar dataKey="valid" fill="var(--color-green)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-xs text-muted">Receipts are {reliability.status}; nothing to count.</p>
      )}
      <div className="flex gap-4 mt-3 text-xs text-text-2">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-green inline-block" />Valid</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-border inline-block" />Eligible</span>
        <span className="ml-auto font-mono text-muted">{formatTokens(eligible)} runs</span>
      </div>
    </div>
  );
}
