import { useState } from "react";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import type { ControlDialogProps } from "./PauseDialog";
import TriggerPicker from "./TriggerPicker";
import { triggerChoices, useControlAction } from "./useControlAction";

export default function RunNowDialog({ workflowId, workflowName, onClose, onChanged }: ControlDialogProps) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(workflowId);
  const choices = triggerChoices(state);
  const done = state.phase === "applied";
  const run = async (trigger?: string) => {
    const next = await send({ action: "run_now", reason: reason || undefined, trigger });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`Run ${workflowName} now`}
      onClose={onClose}
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && !choices && <button className={buttonClass.primary} onClick={() => run()} disabled={state.phase === "busy"}>Run now</button>}
        </>
      }
    >
      <p>Starts the workflow's service once, outside its schedule. The timer is not touched; the receipt carries the run id and the next scheduled elapse.</p>
      <Field label="Reason (optional, goes on the receipt)">
        <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done} />
      </Field>
      {choices ? <TriggerPicker choices={choices} busy={false} onPick={(trigger) => void run(trigger)} /> : <ControlOutcome state={state} />}
    </DialogFrame>
  );
}
