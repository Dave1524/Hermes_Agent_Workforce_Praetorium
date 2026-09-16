import { useState } from "react";
import { WORKFLOWS, MARCUS_TRAJAN_TIMELINE } from "../data";
import HealthBadge from "../components/HealthBadge";
import Dialogs from "../components/Dialogs";
import { AgentAvatar } from "./Overview";

interface Props {
  workflowId: string;
  onBack: () => void;
}

export default function WorkflowDetail({ workflowId, onBack }: Props) {
  const wf = WORKFLOWS.find((w) => w.id === workflowId) ?? WORKFLOWS[0];
  const [dialog, setDialog] = useState<any>(null);
  const [confirmedDialog, setConfirmedDialog] = useState<string | null>(null);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [expandedLineage, setExpandedLineage] = useState<string | null>(null);

  const isStandingResearch = wf.id === "standing-research";
  const isAutoSync = wf.id === "auto-sync";

  const handleConfirm = (type: string) => {
    setConfirmedDialog(type);
    setTimeout(() => setConfirmedDialog(null), 4000);
  };

  return (
    <div className="p-6 max-w-[1100px] mx-auto">
      {/* Back */}
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-text-2 hover:text-text mb-5 transition-colors">
        <span>←</span> Workflows
      </button>

      {/* Header */}
      <div className="bg-surface border border-border rounded-md p-5 mb-5">
        <div className="flex items-start gap-4">
          <AgentAvatar name={wf.agent} size="md" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-lg font-semibold text-text">{wf.name}</h1>
              <HealthBadge health={wf.health} size="md" />
            </div>
            <p className="text-text-2 text-sm mt-1.5 max-w-xl">{wf.purpose}</p>
            <p className="text-muted text-xs mt-2 italic">
              When <span className="not-italic text-text-2">{wf.trigger}</span> occurs, this workflow produces{" "}
              <span className="not-italic text-text-2">{wf.artifact}</span> for Dave, so he can act on it promptly.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            <a href={wf.notionUrl} className="px-3 py-1.5 text-xs font-medium bg-accent-dim border border-accent/30 text-accent rounded hover:bg-accent/20 transition-colors">
              Open latest output
            </a>
            <button onClick={() => setDialog(wf.health === "paused" ? "resume" : "pause")} className="px-3 py-1.5 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">
              {wf.health === "paused" ? "Resume" : "Pause"}
            </button>
            <button onClick={() => setDialog("run")} className="px-3 py-1.5 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">Run now</button>
            <button onClick={() => setDialog("retry")} className={`px-3 py-1.5 text-xs border border-border rounded transition-colors ${wf.retryEnabled ? "text-text-2 hover:bg-surface-3" : "text-muted cursor-not-allowed opacity-60"}`}>Retry</button>
            <button onClick={() => setDialog("stop")} className="px-3 py-1.5 text-xs border border-red/30 text-red rounded hover:bg-red-dim transition-colors">Stop</button>
            <div className="relative">
              <button onClick={() => setOverflowOpen((p) => !p)} className="px-2 py-1.5 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">···</button>
              {overflowOpen && (
                <div className="absolute right-0 top-full mt-1 w-40 bg-surface-3 border border-border rounded shadow-lg z-10">
                  <button onClick={() => { setDialog("schedule"); setOverflowOpen(false); }} className="block w-full text-left px-3 py-2 text-sm text-text-2 hover:bg-surface-2 hover:text-text transition-colors">Change schedule</button>
                  <button onClick={() => { setDialog("retire"); setOverflowOpen(false); }} className="block w-full text-left px-3 py-2 text-sm text-red hover:bg-red-dim transition-colors">Retire workflow</button>
                </div>
              )}
            </div>
          </div>
        </div>

        {confirmedDialog && (
          <div className="mt-4 px-3 py-2 bg-green-dim border border-green/20 rounded text-xs text-green font-mono">
            ✓ Action "{confirmedDialog}" completed successfully.
            {confirmedDialog === "run" && " · Run ID: run-" + wf.id.slice(0, 4) + "-" + Date.now().toString(36)}
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
        {[
          { label: "Last run", value: wf.lastRun, mono: true },
          { label: "Next run", value: wf.nextRun, mono: true },
          { label: "7d reliability", value: `${wf.reliability7d}%`, mono: true },
          { label: "Valid / eligible", value: `${wf.validOutputs} / ${wf.eligibleRuns}`, mono: true },
          { label: "Tokens", value: wf.tokens, mono: true },
          { label: "Cost", value: wf.cost, mono: true },
        ].map((c) => (
          <div key={c.label} className="bg-surface border border-border rounded-md px-3 py-3">
            <div className={`text-base font-semibold ${c.mono ? "font-mono" : ""} text-text`}>{c.value}</div>
            <div className="text-xs text-muted mt-0.5">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Triggers */}
        <Section title="Triggers & schedules">
          <div className="space-y-2">
            <TriggerRow index={1} trigger={wf.trigger} tz="Europe/London" catchup="Disabled" eligibility="No constraints" />
          </div>
        </Section>

        {/* Latest output */}
        <Section title="Latest output">
          <div className="space-y-2">
            <Row label="Title" value={wf.latestOutput} />
            <Row label="Created" value={wf.lastRunTimestamp} />
            <Row label="Status" value={wf.latestOutputStatus} />
            <Row label="Notion destination" value="Dave's workspace · Workflows board" />
            <div className="pt-2 flex gap-2 flex-wrap">
              {["Approve", "Reject", "Edit", "Archive"].map((a) => (
                <button key={a} className="px-2.5 py-1 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors">{a}</button>
              ))}
            </div>
          </div>
        </Section>

        {/* Recent runs */}
        <Section title="Recent runs">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-muted border-b border-border">
                <th className="text-left py-1.5 font-medium">Run</th>
                <th className="text-left py-1.5 font-medium">Outcome</th>
                <th className="text-left py-1.5 font-medium">Duration</th>
                <th className="text-right py-1.5 font-medium">Tokens</th>
                <th className="text-right py-1.5 font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {MOCK_RUNS.filter((r) => r.workflow === wf.id).map((run) => (
                <tr key={run.id} className="hover:bg-surface-3 transition-colors">
                  <td className="py-2 font-mono text-text-2">{run.id.slice(-8)}</td>
                  <td className="py-2"><RunOutcomeBadge outcome={run.outcome} /></td>
                  <td className="py-2 font-mono text-muted">{run.duration}</td>
                  <td className="py-2 font-mono text-muted text-right">{run.tokens}</td>
                  <td className="py-2 font-mono text-muted text-right">{run.cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        {/* Benefit evidence */}
        <Section title="Benefit evidence">
          <p className="text-xs text-muted mb-3">Consumption signals measured independently — not combined into a score.</p>
          <div className="space-y-2">
            {[
              { label: "Opened", value: "6 of 7", pct: 86 },
              { label: "Approved", value: "6 of 7", pct: 86 },
              { label: "Sent or published", value: "4 of 7", pct: 57 },
              { label: "Marked useful", value: "5 of 7", pct: 71 },
            ].map((sig) => (
              <div key={sig.label} className="flex items-center gap-3">
                <span className="text-xs text-text-2 w-32 shrink-0">{sig.label}</span>
                <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${sig.pct}%` }} />
                </div>
                <span className="text-xs font-mono text-muted w-12 text-right">{sig.value}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* Research lineage — Standing Research only */}
      {isStandingResearch && (
        <div className="mt-5">
          <Section title="Research workflow lineage">
            <p className="text-xs text-text-2 mb-4">Select any stage to see evidence. This lineage explains why a particular topic was researched.</p>
            <div className="flex items-start gap-2 flex-wrap">
              {LINEAGE_STAGES.map((stage, i) => (
                <div key={stage.id} className="flex items-start gap-2">
                  <button
                    onClick={() => setExpandedLineage(expandedLineage === stage.id ? null : stage.id)}
                    className={`px-3 py-2 rounded-md text-left text-xs transition-colors border ${
                      expandedLineage === stage.id
                        ? "bg-accent-dim border-accent/40 text-accent"
                        : "bg-surface border-border text-text-2 hover:bg-surface-3"
                    }`}
                  >
                    <div className="font-medium text-[10px] text-muted mb-0.5 uppercase tracking-wider">Stage {i + 1}</div>
                    {stage.label}
                  </button>
                  {i < LINEAGE_STAGES.length - 1 && <span className="text-muted text-lg mt-2">→</span>}
                </div>
              ))}
            </div>
            {expandedLineage && (
              <div className="mt-4 bg-surface border border-border rounded-md p-4">
                {(() => {
                  const stage = LINEAGE_STAGES.find((s) => s.id === expandedLineage)!;
                  return (
                    <>
                      <p className="text-sm font-medium text-text mb-1.5">{stage.label}</p>
                      <p className="text-xs text-text-2">{stage.evidence}</p>
                    </>
                  );
                })()}
              </div>
            )}
          </Section>
        </div>
      )}

      {/* Agent handoff timeline — Auto Sync only */}
      {isAutoSync && (
        <div className="mt-5">
          <Section title="Run & agent-handoff detail · run-dp-20260910-0702">
            <div className="mb-3 grid grid-cols-3 gap-3 text-xs">
              <div><span className="text-muted">Parent run</span><br /><span className="font-mono text-text-2">run-dp-20260910-0702</span></div>
              <div><span className="text-muted">Child run</span><br /><span className="font-mono text-text-2">run-aws-20260910-0902</span></div>
              <div><span className="text-muted">Duration</span><br /><span className="font-mono text-text-2">8m 22s</span></div>
            </div>
            <div className="space-y-0 border-l-2 border-border ml-3">
              {MARCUS_TRAJAN_TIMELINE.map((ev, i) => (
                <TimelineEvent key={i} event={ev} />
              ))}
            </div>
          </Section>
        </div>
      )}

      <Dialogs workflow={wf} dialog={dialog} onClose={() => setDialog(null)} onConfirm={handleConfirm} />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-surface border border-border rounded-md p-4">
      <h3 className="text-xs font-semibold text-text mb-3 uppercase tracking-wider">{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1 text-sm border-b border-border last:border-0">
      <span className="text-text-2">{label}</span>
      <span className="text-text font-mono text-xs pt-0.5">{value}</span>
    </div>
  );
}

function TriggerRow({ index, trigger, tz, catchup, eligibility }: { index: number; trigger: string; tz: string; catchup: string; eligibility: string }) {
  return (
    <div className="bg-surface-2 border border-border rounded p-3 text-xs space-y-1">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-accent font-mono">Trigger {index}</span>
      </div>
      <Row label="Schedule" value={trigger} />
      <Row label="Timezone" value={tz} />
      <Row label="Catch-up" value={catchup} />
      <Row label="Eligibility" value={eligibility} />
    </div>
  );
}

function RunOutcomeBadge({ outcome }: { outcome: string }) {
  const map: Record<string, string> = {
    success: "text-green bg-green-dim", failed: "text-red bg-red-dim",
    incomplete: "text-amber bg-amber-dim", running: "text-blue bg-blue-dim",
  };
  return (
    <span className={`font-mono px-1.5 py-0.5 rounded text-[10px] capitalize ${map[outcome] ?? "text-text-2 bg-surface-3"}`}>{outcome}</span>
  );
}

function TimelineEvent({ event }: { event: any }) {
  const iconMap: Record<string, string> = {
    handoff: "⇄", info: "·", working: "◌", complete: "✓", artifact: "📎",
  };
  const colorMap: Record<string, string> = {
    handoff: "text-accent", info: "text-text-2", working: "text-blue",
    complete: "text-green", artifact: "text-amber",
  };
  return (
    <div className="relative flex items-start gap-3 pl-6 pb-4">
      <div className="absolute left-[-1px] top-0 w-2 h-2 rounded-full bg-border border-2 border-surface translate-x-[-50%] translate-y-1" />
      <div>
        <span className="text-muted font-mono text-xs">{event.time}</span>{" "}
        <span className={`font-medium text-xs ${colorMap[event.type]}`}>{event.actor}</span>{" "}
        <span className={`text-xs mr-1 ${colorMap[event.type]}`}>{iconMap[event.type]}</span>
        <span className="text-xs text-text-2">{event.event}</span>
      </div>
    </div>
  );
}

const MOCK_RUNS = [
  { id: "run-sr-20260910-0901", workflow: "standing-research", outcome: "incomplete", duration: "4m 12s", tokens: "48.2K", cost: "$0.42" },
  { id: "run-sr-20260908-0902", workflow: "standing-research", outcome: "success", duration: "6m 44s", tokens: "52.1K", cost: "$0.46" },
  { id: "run-sr-20260905-0901", workflow: "standing-research", outcome: "success", duration: "5m 58s", tokens: "44.8K", cost: "$0.39" },
  { id: "run-dp-20260910-0702", workflow: "daily-plan", outcome: "success", duration: "1m 58s", tokens: "12.4K", cost: "$0.09" },
  { id: "run-dp-20260909-0700", workflow: "daily-plan", outcome: "success", duration: "2m 04s", tokens: "11.8K", cost: "$0.08" },
  { id: "run-dp-20260908-0701", workflow: "daily-plan", outcome: "success", duration: "1m 48s", tokens: "10.9K", cost: "$0.07" },
  { id: "run-aws-20260910-1500", workflow: "auto-sync", outcome: "running", duration: "—", tokens: "—", cost: "—" },
  { id: "run-aws-20260910-1400", workflow: "auto-sync", outcome: "success", duration: "38s", tokens: "8.9K", cost: "$0.06" },
  { id: "run-aws-20260910-1300", workflow: "auto-sync", outcome: "success", duration: "35s", tokens: "8.2K", cost: "$0.05" },
  { id: "run-ac-20260910-1100", workflow: "augustus-content", outcome: "incomplete", duration: "3m 22s", tokens: "31.7K", cost: "$0.28" },
  { id: "run-ac-20260909-1102", workflow: "augustus-content", outcome: "success", duration: "4m 10s", tokens: "34.2K", cost: "$0.30" },
  { id: "run-kd-20260909-1702", workflow: "knowledge-digest", outcome: "success", duration: "5m 28s", tokens: "22.1K", cost: "$0.19" },
  { id: "run-fe-20260902-0604", workflow: "fleet-eval", outcome: "success", duration: "8m 12s", tokens: "19.3K", cost: "$0.16" },
];

const LINEAGE_STAGES = [
  {
    id: "candidates", label: "Candidate sources",
    evidence: "32 sources monitored: RSS feeds, newsletters, curated reading lists. Scanned by Claudius on each eligible run. Last scan: 2026-09-10 09:01.",
  },
  {
    id: "criteria", label: "Selection criteria",
    evidence: "Topics must: (1) appear in ≥2 sources, (2) align with stated research interests, (3) not duplicate a proposal in the last 30 days. Criteria version: v4.",
  },
  {
    id: "selected", label: "Selected topic & reason",
    evidence: "Topic: Byzantine fiscal policy (6th–7th century). Reason: appeared in 4 sources, matches stated interest in late antique economic history, no duplicate in 30-day window.",
  },
  {
    id: "trigger", label: "Schedule / trigger",
    evidence: "Run triggered by cron schedule: Tue/Thu 09:00 Europe/London. Run initiated at 09:01:14. No catch-up. Eligible.",
  },
  {
    id: "run", label: "Claudius research run",
    evidence: "Run ID: run-sr-20260910-0901. Duration: 4m 12s. Outcome: incomplete. No proposal or valid decline produced. Contract requires one of the two artifacts.",
  },
  {
    id: "notion", label: "Notion proposal",
    evidence: "No proposal was created in this run. Previous proposal (Sep 8): 'Sassanid trade routes' — approved by Dave on Sep 9.",
  },
  {
    id: "action", label: "Dave's next action",
    evidence: "Review run log (run-sr-20260910-0901), then either retry the run or provide a manual decline note in the Standing Research Notion page.",
  },
];
