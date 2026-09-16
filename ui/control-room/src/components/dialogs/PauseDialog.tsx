import { useState } from "react";
import DependencyNotice from "@/components/DependencyNotice";
import type { DependentView } from "@/model/requires";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import { useControlAction } from "./useControlAction";

export interface ControlDialogProps {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
  onChanged: () => void;
}

export interface DependencyProps {
  requiredBy: DependentView[];
  guards: string | null;
}

export default function PauseDialog({ workflowId, workflowName, onClose, onChanged, requiredBy, guards }: ControlDialogProps & DependencyProps) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(workflowId);
  const done = state.phase === "applied";
  const apply = async () => {
    const next = await send({ action: "pause", reason: reason || undefined });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`Pause ${workflowName}`}
      onClose={onClose}
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && <button className={buttonClass.primary} onClick={apply} disabled={state.phase === "busy"}>Pause</button>}
        </>
      }
    >
      <p>The timer is disabled and stops scheduling runs. A run already in progress finishes; nothing is killed.</p>
      <DependencyNotice action="pause" requiredBy={requiredBy} guards={guards} />
      <Field label="Reason (optional, goes on the receipt)">
        <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done} />
      </Field>
      <ControlOutcome state={state} />
    </DialogFrame>
  );
}
