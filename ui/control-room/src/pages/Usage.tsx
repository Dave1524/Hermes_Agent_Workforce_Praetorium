import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usageResponseSchema } from "@/api/schemas/usage";
import { workflowListResponseSchema } from "@/api/schemas/workflow";
import AgentAvatar from "@/components/AgentAvatar";
import DataStatusStrip from "@/components/DataStatusStrip";
import { CostCell, NotMeasured, UsageCell } from "@/components/MeasurementCell";
import { Stat } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import { formatTokens } from "@/model/tokens";
import { type AgentUsage, toAgentUsage, totalCost } from "@/model/usage";
import { toWorkflowRow } from "@/model/workflowRow";
import { usePageResource, useSecondaryResource } from "@/shell/usePageResource";

const measuredTokens = (rows: AgentUsage[]): { total: number; measured: number } =>
  rows.reduce((acc, r) => (r.usage.status === "measured" ? { total: acc.total + r.usage.value.total, measured: acc.measured + 1 } : acc), { total: 0, measured: 0 });

export default function Usage() {
  const usage = usePageResource("/api/v1/usage", usageResponseSchema);
  const workflows = useSecondaryResource("/api/v1/workflows", workflowListResponseSchema);
  if (usage.status === "error" && usage.error) return <ErrorNotice what="usage" error={usage.error} onRetry={usage.refresh} />;
  if (!usage.data) return <Loading what="usage" />;
  const agents = usage.data.items.map(toAgentUsage);
  const tokens = measuredTokens(agents);
  const cost = totalCost(agents);
  const chart = agents.flatMap((a) => (a.usage.status === "measured" ? [{ name: a.agent, Input: a.usage.value.input, Output: a.usage.value.output, Cache: a.usage.value.cache }] : []));
  const rows = (workflows.data?.items ?? []).map(toWorkflowRow);

  return (
    <>
      <DataStatusStrip status={usage.data.dataStatus} />
      <div className="p-6 max-w-[1100px] mx-auto space-y-6">
        <div className="grid grid-cols-3 gap-3">
          <div data-testid="stat-tokens"><Stat label={`Tokens (${tokens.measured} of ${agents.length} agents measured)`} value={tokens.measured === 0 ? "unavailable" : formatTokens(tokens.total)} /></div>
          <div data-testid="stat-cost"><Stat label={`Cost (${cost.measured} of ${agents.length} agents measured)`} value={cost.amount === null ? "unavailable" : `${cost.amount.toFixed(2)} ${cost.currency}`} /></div>
          <div data-testid="stat-measured"><Stat label="Agents with measured usage" value={`${tokens.measured} / ${agents.length}`} /></div>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-text mb-3">Agent token usage</h2>
          <div className="bg-surface border border-border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted">
                  <th className="text-left px-4 py-2.5 font-medium">Agent</th>
                  <th className="text-right px-4 py-2.5 font-medium">Runs</th>
                  <th className="text-right px-4 py-2.5 font-medium">Input</th>
                  <th className="text-right px-4 py-2.5 font-medium">Output</th>
                  <th className="text-right px-4 py-2.5 font-medium">Cache</th>
                  <th className="text-right px-4 py-2.5 font-medium">Total</th>
                  <th className="text-right px-4 py-2.5 font-medium">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {agents.map((a) => (
                  <tr key={a.agent} className="hover:bg-surface-3 transition-colors" data-testid="agent-row">
                    <td className="px-4 py-3">
                      <RouteLink to={{ name: "agent", id: a.agent }} className="flex items-center gap-2.5 hover:text-accent">
                        <AgentAvatar name={a.agent} />
                        <span className="text-text font-medium">{a.agent}</span>
                      </RouteLink>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-text-2">{a.runs ?? "—"}</td>
                    {a.usage.status === "measured" ? (
                      <>
                        <td className="px-4 py-3 text-right font-mono text-xs text-text-2">{formatTokens(a.usage.value.input)}</td>
                        <td className="px-4 py-3 text-right font-mono text-xs text-text-2">{formatTokens(a.usage.value.output)}</td>
                        <td className="px-4 py-3 text-right font-mono text-xs text-text-2">{formatTokens(a.usage.value.cache)}</td>
                        <td className="px-4 py-3 text-right"><UsageCell usage={a.usage} /></td>
                      </>
                    ) : (
                      <td colSpan={4} className="px-4 py-3 text-right"><NotMeasured status={a.usage.status} /></td>
                    )}
                    <td className="px-4 py-3 text-right"><CostCell cost={a.cost} /></td>
                  </tr>
                ))}
                {agents.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-text-2 text-sm">No usage recorded.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-text mb-3">Tokens per agent (measured only)</h2>
          <div className="bg-surface border border-border rounded-md p-4" data-testid="usage-chart">
            {chart.length === 0 ? (
              <p className="text-xs text-muted">No agent has measured usage; nothing to chart.</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chart} barCategoryGap="30%">
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--color-text-2)" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--color-muted)" }} axisLine={false} tickLine={false} tickFormatter={(v: number) => formatTokens(v)} />
                  <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={{ background: "var(--color-surface-3)", border: "1px solid var(--color-border)", fontSize: 11 }} formatter={(v) => formatTokens(Number(v))} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Input" stackId="a" fill="var(--color-blue)" />
                  <Bar dataKey="Output" stackId="a" fill="var(--color-green)" />
                  <Bar dataKey="Cache" stackId="a" fill="var(--color-border-2)" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div>
          <h2 className="text-sm font-semibold text-text mb-3">Last run per workflow</h2>
          <div className="bg-surface border border-border rounded-md overflow-hidden">
            {workflows.status === "error" && workflows.error && <ErrorNotice what="the workflows" error={workflows.error} onRetry={workflows.refresh} />}
            {!workflows.data && workflows.status !== "error" && <Loading what="workflows" />}
            {workflows.data && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted">
                    <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
                    <th className="text-left px-4 py-2.5 font-medium">Owner</th>
                    <th className="text-right px-4 py-2.5 font-medium">Tokens</th>
                    <th className="text-right px-4 py-2.5 font-medium">Cost</th>
                    <th className="text-right px-4 py-2.5 font-medium">Valid artifact rate</th>
                    <th className="text-right px-4 py-2.5 font-medium">Receipts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((r) => (
                    <tr key={r.id} className="hover:bg-surface-3 transition-colors">
                      <td className="px-4 py-2.5"><RouteLink to={{ name: "workflow", id: r.id }} className="text-text hover:text-accent">{r.name}</RouteLink></td>
                      <td className="px-4 py-2.5 text-text-2">{r.owner ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right"><UsageCell usage={r.usage} /></td>
                      <td className="px-4 py-2.5 text-right"><CostCell cost={r.cost} /></td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-text-2">{r.validArtifactRate === null ? "—" : `${Math.round(r.validArtifactRate * 100)}%`}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-muted">{r.receiptCount ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
