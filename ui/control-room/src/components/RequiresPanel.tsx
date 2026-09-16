import type { DependentView, RequirementView } from "@/model/requires";
import { Panel } from "./Panel";
import RequirementLink from "./RequirementLink";
import RouteLink from "./RouteLink";

const satisfiedAttr = (satisfied: boolean | null): string => (satisfied === null ? "unknown" : String(satisfied));
const satisfiedTone = (satisfied: boolean | null): string => (satisfied === null ? "text-muted" : satisfied ? "text-green" : "text-red");
const enabledAttr = (enabled: boolean | null): string => (enabled === null ? "unknown" : String(enabled));
const enabledLabel = (enabled: boolean | null): string => (enabled === null ? "unknown" : enabled ? "enabled" : "paused");

function RequirementRow({ requirement }: { requirement: RequirementView }) {
  return (
    <li className="flex justify-between gap-4 py-1 text-xs border-b border-border last:border-0 font-mono" data-testid="requirement" data-satisfied={satisfiedAttr(requirement.satisfied)}>
      <span className="min-w-0 break-all">
        <RequirementLink requirement={requirement} />
        {requirement.scope && <span className="text-muted"> ({requirement.scope})</span>}
      </span>
      <span className={`shrink-0 ${satisfiedTone(requirement.satisfied)}`}>{requirement.state}</span>
    </li>
  );
}

function DependentRow({ dependent }: { dependent: DependentView }) {
  return (
    <li className="flex justify-between gap-4 py-1 text-xs border-b border-border last:border-0 font-mono" data-testid="dependent" data-enabled={enabledAttr(dependent.enabled)}>
      <RouteLink to={{ name: "workflow", id: dependent.workflow }} className="text-accent hover:underline min-w-0 break-all">{dependent.workflow}</RouteLink>
      <span className={`shrink-0 ${dependent.enabled ? "text-green" : "text-muted"}`}>{enabledLabel(dependent.enabled)}</span>
    </li>
  );
}

export default function RequiresPanel({ requires, requiredBy }: { requires: RequirementView[]; requiredBy: DependentView[] }) {
  return (
    <Panel title="Requires / Required by">
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1">Requires</div>
      {requires.length === 0 ? <p className="text-xs text-muted">This workflow requires nothing beyond its own unit.</p> : <ul>{requires.map((r) => <RequirementRow key={`${r.scope}/${r.unit}`} requirement={r} />)}</ul>}
      <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1 mt-3">Required by</div>
      {requiredBy.length === 0 ? <p className="text-xs text-muted">Nothing requires this workflow.</p> : <ul>{requiredBy.map((d) => <DependentRow key={d.workflow} dependent={d} />)}</ul>}
      <p className="text-xs text-muted mt-3">A requirement that is down refuses every run at pre-flight; unknown means the bus answered nothing and is never a refusal.</p>
    </Panel>
  );
}
