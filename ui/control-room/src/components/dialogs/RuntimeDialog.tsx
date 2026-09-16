import { useState } from "react";
import type { RuntimeActionId } from "@/api/schemas/control";
import DependencyNotice from "@/components/DependencyNotice";
import type { AgentView } from "@/model/agent";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import { useControlAction } from "./useControlAction";

export const RUNTIME_LABELS: Record<RuntimeActionId, string> = {
  start: "Start agent now",
  stop: "Stop agent now",
  restart: "Restart agent now",
};

interface Props {
  action: RuntimeActionId;
  agent: AgentView;
  unit: string;
  onClose: () => void;
  onChanged: () => void;
}

const CHECK_LOADED = "~/.config/buzz-team/check-loaded.sh";
const REASON_REQUIRED: Record<RuntimeActionId, boolean> = { start: false, stop: true, restart: true };
const TONE: Record<RuntimeActionId, "default" | "danger"> = { start: "default", stop: "danger", restart: "danger" };

// The session verbs only: the unit file's enable state is a fact the dialog states and never changes.
const bootPolicy = (unitFileState: string | null): string => {
  if (unitFileState === "enabled") return "Unit file enabled: this runtime also comes back after a reboot.";
  if (unitFileState === "disabled") return "Unit file disabled: this changes the session only; it will not come back after a reboot.";
  return `Boot policy unknown (unit file state ${unitFileState ?? "unread"}).`;
};

function Explanation({ action, unit }: { action: RuntimeActionId; unit: string }) {
  if (action === "start") {
    return (
      <>
        <p>Starts <span className="font-mono">{unit}</span> in the user manager now. This sends <span className="font-mono">confirm: true</span>.</p>
        <p className="text-amber">If Buzz Desktop on the Mac is also hosting this agent, both reply to every mention from one pubkey.</p>
        <p>Verify with <span className="font-mono">{CHECK_LOADED}</span> once it is up.</p>
      </>
    );
  }
  if (action === "stop") {
    return <p>Stops <span className="font-mono">{unit}</span> now. A turn in progress is lost; the receipt records the stop. This sends <span className="font-mono">confirm: true</span> and needs a reason.</p>;
  }
  return (
    <>
      <p>Stops and starts <span className="font-mono">{unit}</span> now, so it re-reads its .env and .prompt. A turn in progress is lost. This sends <span className="font-mono">confirm: true</span> and needs a reason.</p>
      <p>Verify with <span className="font-mono">{CHECK_LOADED}</span> once it is back.</p>
    </>
  );
}

export default function RuntimeDialog({ action, agent, unit, onClose, onChanged }: Props) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(unit);
  const done = state.phase === "applied";
  const needsReason = REASON_REQUIRED[action];
  const apply = async () => {
    const next = await send({ action, reason: reason || undefined });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`${RUNTIME_LABELS[action]}: ${agent.name}`}
      onClose={onClose}
      tone={TONE[action]}
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && (
            <button className={TONE[action] === "danger" ? buttonClass.danger : buttonClass.primary} onClick={apply} disabled={state.phase === "busy" || (needsReason && !reason.trim())}>
              {RUNTIME_LABELS[action]}
            </button>
          )}
        </>
      }
    >
      <Explanation action={action} unit={unit} />
      {action !== "start" && <DependencyNotice action={action} requiredBy={agent.requiredBy} guards={null} />}
      <p className="text-xs text-muted" data-testid="boot-policy">{bootPolicy(agent.runtime.unitFileState)}</p>
      <Field label={needsReason ? "Reason (required)" : "Reason (optional)"}>
        <textarea className={`${inputClass} min-h-[4rem]`} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done} required={needsReason} />
      </Field>
      <ControlOutcome state={state} />
    </DialogFrame>
  );
}
