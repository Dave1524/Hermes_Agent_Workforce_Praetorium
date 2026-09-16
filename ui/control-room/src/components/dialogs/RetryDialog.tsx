import { useState } from "react";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import type { ControlDialogProps } from "./PauseDialog";
import TriggerPicker from "./TriggerPicker";
import { triggerChoices, useControlAction } from "./useControlAction";

interface Props extends ControlDialogProps {
  retryOf: string | null;
  disabledReason: string | null;
}

export default function RetryDialog({ workflowId, workflowName, retryOf, disabledReason, onClose, onChanged }: Props) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(workflowId);
  const choices = triggerChoices(state);
  const done = state.phase === "applied";
  const blocked = disabledReason !== null || retryOf === null;
  const retry = async (trigger?: string) => {
    const next = await send({ action: "retry", retry_of: retryOf, reason: reason || undefined, trigger });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`Retry ${workflowName}`}
      onClose={onClose}
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && !choices && <button className={buttonClass.primary} onClick={() => retry()} disabled={blocked || state.phase === "busy"}>Retry {retryOf ?? ""}</button>}
        </>
      }
    >
      <p>Re-runs the last run's unit once, recorded against that run (<span className="font-mono">retry_of</span>). The broker refuses unless the contract declares an idempotent operation.</p>
      {disabledReason && <p className="text-xs text-amber" data-testid="retry-disabled">Retry is disabled: {disabledReason}</p>}
      {retryOf === null && <p className="text-xs text-amber" data-testid="retry-disabled">No last run to retry.</p>}
      <Field label="Reason (optional, goes on the receipt)">
        <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done || blocked} />
      </Field>
      {choices ? <TriggerPicker choices={choices} busy={false} onPick={(trigger) => void retry(trigger)} /> : <ControlOutcome state={state} />}
    </DialogFrame>
  );
}
