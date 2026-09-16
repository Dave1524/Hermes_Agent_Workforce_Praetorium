import { useState } from "react";
import { type RuntimeActionId, runtimeActionIdSchema } from "@/api/schemas/control";
import { buttonClass } from "@/components/dialogs/DialogFrame";
import RuntimeDialog, { RUNTIME_LABELS } from "@/components/dialogs/RuntimeDialog";
import type { AgentView } from "@/model/agent";
import LastActionPanel from "./LastActionPanel";
import { Panel } from "./Panel";

interface Props {
  agent: AgentView;
  onChanged: () => void;
}

interface RuntimeAction {
  id: RuntimeActionId;
  enabled: boolean;
  reason: string | null;
}

const runtimeActions = (agent: AgentView): RuntimeAction[] =>
  agent.actions.flatMap((a) => {
    const id = runtimeActionIdSchema.safeParse(a.id);
    return id.success ? [{ id: id.data, enabled: a.enabled, reason: a.reason }] : [];
  });

export default function AgentControls({ agent, onChanged }: Props) {
  const [open, setOpen] = useState<RuntimeActionId | null>(null);
  const unit = agent.runtime.unit;
  const actions = runtimeActions(agent);

  return (
    <Panel title="Controls">
      <div data-testid="agent-controls">
        <div className="flex items-center gap-2 flex-wrap">
          {actions.map((a) => (
            <button
              key={a.id}
              type="button"
              className={a.id === "start" ? buttonClass.primary : buttonClass.danger}
              disabled={!a.enabled || !unit}
              title={a.enabled ? undefined : (a.reason ?? "not available")}
              onClick={() => setOpen(a.id)}
            >
              {RUNTIME_LABELS[a.id]}
            </button>
          ))}
          {actions.length === 0 && <span className="text-xs text-muted">No runtime actions offered for this agent{unit ? "" : " (no runtime unit)"}.</span>}
        </div>
        <div className="mt-3 text-xs text-muted">
          Session verbs on the user unit, through the control broker, each with a receipt. Boot policy is shown on the card and never changed from here.
        </div>
        <div className="mt-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1.5">Last control action</div>
          <LastActionPanel lastAction={agent.lastAction} />
        </div>
      </div>
      {open && unit && <RuntimeDialog action={open} agent={agent} unit={unit} onClose={() => setOpen(null)} onChanged={onChanged} />}
    </Panel>
  );
}
