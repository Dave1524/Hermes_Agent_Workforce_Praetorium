import { useState } from "react";
import DependencyNotice from "@/components/DependencyNotice";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import type { ControlDialogProps, DependencyProps } from "./PauseDialog";
import { useControlAction } from "./useControlAction";

export default function StopDialog({ workflowId, workflowName, onClose, onChanged, requiredBy, guards }: ControlDialogProps & DependencyProps) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(workflowId);
  const done = state.phase === "applied";
  const stop = async () => {
    const next = await send({ action: "stop", reason });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`Stop ${workflowName}`}
      onClose={onClose}
      tone="danger"
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && <button className={buttonClass.danger} onClick={stop} disabled={state.phase === "busy" || !reason.trim()}>Stop the running service</button>}
        </>
      }
    >
      <p>Stops the running service now. The run ends without a terminal outcome of its own; the receipt records the stop. This sends <span className="font-mono">confirm: true</span> and needs a reason.</p>
      <DependencyNotice action="stop" requiredBy={requiredBy} guards={guards} />
      <Field label="Reason (required)">
        <textarea className={`${inputClass} min-h-[4rem]`} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done} required />
      </Field>
      <ControlOutcome state={state} />
    </DialogFrame>
  );
}
