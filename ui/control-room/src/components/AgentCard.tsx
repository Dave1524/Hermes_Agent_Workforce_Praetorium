import type { AgentView } from "@/model/agent";
import { ROLE_LABELS, ROLES } from "@/model/role";
import AgentAvatar from "./AgentAvatar";
import HealthBadge from "./HealthBadge";
import { CostCell, UsageCell } from "./MeasurementCell";
import OutcomeBadge from "./OutcomeBadge";
import RouteLink from "./RouteLink";
import RuntimeChip from "./RuntimeChip";
import When from "./When";

function Fact({ label, children, testId }: { label: string; children: React.ReactNode; testId?: string }) {
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted">{label}</div>
      <div className="text-xs font-mono text-text mt-0.5" data-testid={testId}>{children}</div>
    </div>
  );
}

function OwnedWorkflows({ agent }: { agent: AgentView }) {
  if (agent.ownedWorkflows.length === 0) return <p className="text-xs text-muted">Owns no workflow.</p>;
  return (
    <div className="space-y-1">
      {ROLES.filter((role) => role !== "agent-runtime").map((role) => {
        const owned = agent.ownedWorkflows.filter((w) => w.role === role);
        if (owned.length === 0) return null;
        return (
          <div key={role} className="text-xs">
            <span className="text-muted">{ROLE_LABELS[role]}s: </span>
            {owned.map((w, i) => (
              <span key={w.id}>
                {i > 0 && ", "}
                <RouteLink to={{ name: "workflow", id: w.id }} className="font-mono text-accent hover:underline">{w.id}</RouteLink>
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export default function AgentCard({ agent, link = true }: { agent: AgentView; link?: boolean }) {
  return (
    <section className="bg-surface border border-border rounded-md p-4" data-testid="agent-card" data-agent={agent.name}>
      <div className="flex items-start gap-3">
        <AgentAvatar name={agent.name} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {link ? <RouteLink to={{ name: "agent", id: agent.name }} className="text-base font-semibold text-text hover:text-accent">{agent.name}</RouteLink> : <h2 className="text-base font-semibold text-text">{agent.name}</h2>}
            <HealthBadge health={agent.health} />
            <RuntimeChip runtime={agent.runtime} />
            {agent.runtime.unitFileState && <span className="text-[10px] font-mono text-muted" data-testid="boot-policy-chip">boot: {agent.runtime.unitFileState}</span>}
          </div>
          {agent.title && <p className="text-xs text-text-2 mt-0.5">{agent.title}</p>}
          <p className="text-[10px] font-mono text-muted mt-0.5">{agent.harness ?? "harness unknown"}{agent.runtime.unit && ` · ${agent.runtime.unit}`}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
        <Fact label="Last turn" testId="last-turn">
          <span className="flex items-center gap-1.5"><When iso={agent.lastTurn?.endedAt ?? agent.lastTurn?.startedAt} />{agent.lastTurn && <OutcomeBadge outcome={agent.lastTurn.outcome} />}</span>
        </Fact>
        <Fact label="Turns 7d" testId="turns-7d">{agent.turns7d ?? "—"}</Fact>
        <Fact label="Tokens 7d"><UsageCell usage={agent.usage7d} /></Fact>
        <Fact label="Cost 7d"><CostCell cost={agent.cost7d} /></Fact>
      </div>
      <div className="mt-4">
        <OwnedWorkflows agent={agent} />
        {agent.requiredBy.length > 0 && (
          <p className="text-xs mt-1" data-testid="required-by">
            <span className="text-muted">Required by: </span>
            {agent.requiredBy.map((d, i) => (
              <span key={d.workflow}>
                {i > 0 && ", "}
                <RouteLink to={{ name: "workflow", id: d.workflow }} className="font-mono text-accent hover:underline">{d.workflow}</RouteLink>
                {d.enabled === false && <span className="text-muted"> (paused)</span>}
              </span>
            ))}
          </p>
        )}
      </div>
    </section>
  );
}
