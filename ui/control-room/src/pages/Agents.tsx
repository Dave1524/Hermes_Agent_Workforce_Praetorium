import { agentListResponseSchema } from "@/api/schemas/agent";
import AgentCard from "@/components/AgentCard";
import DataStatusStrip from "@/components/DataStatusStrip";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import { toAgent } from "@/model/agent";
import { usePageResource } from "@/shell/usePageResource";

export default function Agents() {
  const agents = usePageResource("/api/v1/agents", agentListResponseSchema);
  if (agents.status === "error" && agents.error) return <ErrorNotice what="the agents" error={agents.error} onRetry={agents.refresh} />;
  if (!agents.data) return <Loading what="the agents" />;
  const items = agents.data.items.map(toAgent);
  const up = items.filter((a) => a.runtime.status === "up").length;
  return (
    <>
      <DataStatusStrip status={agents.data.dataStatus} />
      <div className="p-6 max-w-[1200px] mx-auto">
        <div className="flex items-center gap-3 mb-5">
          <p className="text-xs text-muted">One card per manifest; the runtime is its buzz-agent@ unit, read from the bus. Start, stop and restart live on the agent page.</p>
          <span className="text-xs text-muted ml-auto font-mono" data-testid="agent-count">{items.length} agents · {up} up</span>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {items.map((agent) => <AgentCard key={agent.name} agent={agent} />)}
        </div>
        {items.length === 0 && <p className="text-sm text-text-2 text-center p-8">No agent manifests found.</p>}
      </div>
    </>
  );
}
