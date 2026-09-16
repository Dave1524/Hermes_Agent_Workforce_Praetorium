import { agentDetailResponseSchema } from "@/api/schemas/agent";
import { runListResponseSchema } from "@/api/schemas/run";
import AgentCard from "@/components/AgentCard";
import AgentControls from "@/components/AgentControls";
import DataStatusStrip from "@/components/DataStatusStrip";
import { Panel, Row } from "@/components/Panel";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import RunsTable from "@/components/RunsTable";
import { toAgent } from "@/model/agent";
import { toRun } from "@/model/run";
import { usePageResource, useSecondaryResource } from "@/shell/usePageResource";

export default function AgentDetail({ name }: { name: string }) {
  const runtimeId = `buzz-agent@${name}`;
  const agent = usePageResource(`/api/v1/agents/${encodeURIComponent(name)}`, agentDetailResponseSchema);
  const turns = useSecondaryResource(`/api/v1/workflows/${encodeURIComponent(runtimeId)}/runs`, runListResponseSchema);

  if (agent.status === "error" && agent.error) return <ErrorNotice what={`agent ${name}`} error={agent.error} onRetry={agent.refresh} />;
  if (!agent.data) return <Loading what={`agent ${name}`} />;
  const a = toAgent(agent.data.items);

  return (
    <>
      <DataStatusStrip status={agent.data.dataStatus} />
      <div className="p-6 max-w-[1100px] mx-auto space-y-5">
        <RouteLink to={{ name: "agents" }} className="inline-flex items-center gap-1.5 text-sm text-text-2 hover:text-text transition-colors">
          <span aria-hidden>←</span> Agents
        </RouteLink>
        <AgentCard agent={a} link={false} />
        <AgentControls agent={a} onChanged={agent.refresh} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Panel title="Recent turns">
            {turns.status === "error" && turns.error && <ErrorNotice what="the turns" error={turns.error} onRetry={turns.refresh} />}
            {!turns.data && turns.status !== "error" && <Loading what="turns" />}
            {turns.data && <RunsTable runs={turns.data.items.map(toRun)} empty="No turns receipted." />}
          </Panel>
          <Panel title="Runtime">
            <Row label="Unit">{a.runtime.unit ? <RouteLink to={{ name: "workflow", id: a.runtime.unit }} className="text-accent hover:underline">{a.runtime.unit}</RouteLink> : "—"}</Row>
            <Row label="Scope">{a.runtime.scope ?? "—"}</Row>
            <Row label="State">{a.runtime.state}</Row>
            <Row label="Boot">{a.runtime.unitFileState ?? "—"}</Row>
            <Row label="Harness">{a.harness ?? "—"}</Row>
            <Row label="Manifest">{a.manifest ?? "—"}</Row>
            <p className="text-xs text-muted mt-3">Start, stop and restart act on the session; the boot policy is read from the unit file and never changed here.</p>
          </Panel>
        </div>
      </div>
    </>
  );
}
