import { AGENT_USAGE, WORKFLOWS } from "../data";
import { AgentAvatar, Unavailable } from "./Overview";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";

function fmtTokens(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function Usage() {
  const chartData = AGENT_USAGE.filter((a) => a.available).map((a) => ({
    name: a.name,
    Input: a.inputTokens! / 1000,
    Output: a.outputTokens! / 1000,
  }));

  const workflowData = WORKFLOWS.map((w) => ({
    name: w.name.length > 20 ? w.name.slice(0, 18) + "…" : w.name,
    fullName: w.name,
    agent: w.agent,
    tokens: w.tokens,
    cost: w.cost,
    reliability: w.reliability7d,
  }));

  const totalCost = AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.cost ?? 0), 0);
  const totalTokens = AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.totalTokens ?? 0), 0);

  return (
    <div className="p-6 max-w-[1100px] mx-auto space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-surface border border-border rounded-md px-4 py-3">
          <div className="text-xl font-mono font-semibold text-text">{fmtTokens(totalTokens)}</div>
          <div className="text-xs text-muted mt-0.5">Total tokens today</div>
        </div>
        <div className="bg-surface border border-border rounded-md px-4 py-3">
          <div className="text-xl font-mono font-semibold text-text">${totalCost.toFixed(2)}</div>
          <div className="text-xs text-muted mt-0.5">Total cost today</div>
        </div>
        <div className="bg-surface border border-border rounded-md px-4 py-3">
          <div className="text-xl font-mono font-semibold text-text">4 / 5</div>
          <div className="text-xs text-muted mt-0.5">Agents with available telemetry</div>
        </div>
      </div>

      {/* Agent usage table */}
      <div>
        <h2 className="text-sm font-semibold text-text mb-3">Agent token usage</h2>
        <div className="bg-surface border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
                <th className="text-left px-4 py-2.5 font-medium">Agent</th>
                <th className="text-right px-4 py-2.5 font-medium">Input tokens</th>
                <th className="text-right px-4 py-2.5 font-medium">Output tokens</th>
                <th className="text-right px-4 py-2.5 font-medium">Total tokens</th>
                <th className="text-right px-4 py-2.5 font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {AGENT_USAGE.map((a) => (
                <tr key={a.name} className="hover:bg-surface-3 transition-colors">
                  <td className="px-4 py-3 flex items-center gap-2.5">
                    <AgentAvatar name={a.name} size="sm" />
                    <span className="text-text font-medium">{a.name}</span>
                  </td>
                  {a.available ? (
                    <>
                      <td className="px-4 py-3 text-right font-mono text-text-2 text-xs">{fmtTokens(a.inputTokens!)}</td>
                      <td className="px-4 py-3 text-right font-mono text-text-2 text-xs">{fmtTokens(a.outputTokens!)}</td>
                      <td className="px-4 py-3 text-right font-mono text-text text-xs">{fmtTokens(a.totalTokens!)}</td>
                      <td className="px-4 py-3 text-right font-mono text-text-2 text-xs">${a.cost!.toFixed(2)}</td>
                    </>
                  ) : (
                    <td colSpan={4} className="px-4 py-3 text-right">
                      <Unavailable />
                    </td>
                  )}
                </tr>
              ))}
              <tr className="border-t border-border-2 bg-surface-3 font-medium">
                <td className="px-4 py-2.5 text-xs text-text-2">Total (available agents)</td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-text">
                  {fmtTokens(AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.inputTokens ?? 0), 0))}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-text">
                  {fmtTokens(AGENT_USAGE.filter((a) => a.available).reduce((s, a) => s + (a.outputTokens ?? 0), 0))}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-text">{fmtTokens(totalTokens)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-xs text-text">${totalCost.toFixed(2)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Chart */}
      <div>
        <h2 className="text-sm font-semibold text-text mb-3">Token distribution by agent (Input vs Output)</h2>
        <div className="bg-surface border border-border rounded-md p-4">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} barCategoryGap="35%">
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#a4a4b0" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#5e5e6a" }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}K`} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.03)" }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="bg-surface-3 border border-border rounded px-3 py-2 text-xs font-mono">
                      <p className="text-text font-medium mb-1">{label}</p>
                      {payload.map((p: any) => (
                        <p key={p.dataKey} style={{ color: p.color }}>{p.dataKey}: {p.value}K</p>
                      ))}
                    </div>
                  );
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#a4a4b0" }} />
              <Bar dataKey="Input" fill="#4e8fd8" radius={[2, 2, 0, 0]} />
              <Bar dataKey="Output" fill="#c9a44a" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Workflow token breakdown */}
      <div>
        <h2 className="text-sm font-semibold text-text mb-3">Token usage by workflow</h2>
        <div className="bg-surface border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
                <th className="text-left px-4 py-2.5 font-medium">Workflow</th>
                <th className="text-left px-4 py-2.5 font-medium">Agent</th>
                <th className="text-right px-4 py-2.5 font-medium">Tokens</th>
                <th className="text-right px-4 py-2.5 font-medium">Cost</th>
                <th className="text-right px-4 py-2.5 font-medium">7d reliability</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {workflowData.map((w) => (
                <tr key={w.fullName} className="hover:bg-surface-3 transition-colors">
                  <td className="px-4 py-2.5 text-text">{w.fullName}</td>
                  <td className="px-4 py-2.5 text-text-2 text-xs">{w.agent}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-text-2">{w.tokens}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-text-2">{w.cost}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-text-2">{w.reliability}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
