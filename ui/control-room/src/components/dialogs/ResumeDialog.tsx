import { useState } from "react";
import type { Implication } from "@/api/schemas/control";
import { formatUtc } from "@/model/time";
import ControlOutcome from "./ControlOutcome";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import type { ControlDialogProps } from "./PauseDialog";
import { useControlAction } from "./useControlAction";

export default function ResumeDialog({ workflowId, workflowName, onClose, onChanged }: ControlDialogProps) {
  const [reason, setReason] = useState("");
  const { state, send } = useControlAction(workflowId);
  const previewed = state.phase === "previewed" ? state : null;
  const done = state.phase === "applied";
  const preview = () => send({ action: "resume", stage: "preview", reason: reason || undefined });
  const apply = async () => {
    if (!previewed) return;
    const next = await send({ action: "resume", stage: "apply", preview_token: previewed.previewToken, reason: reason || undefined });
    if (next.phase === "applied") onChanged();
  };
  return (
    <DialogFrame
      title={`Resume ${workflowName}`}
      onClose={onClose}
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {!done && !previewed && <button className={buttonClass.primary} onClick={preview} disabled={state.phase === "busy"}>Preview</button>}
          {previewed && <button className={buttonClass.primary} onClick={apply} disabled={state.phase !== "previewed"}>Apply with this preview</button>}
        </>
      }
    >
      <p>Resume is two-stage: the broker previews what enabling the timer implies — in particular whether a persistent timer fires a missed elapse immediately — and applies only with that preview's token (valid 10 minutes).</p>
      <Field label="Reason (optional, goes on the receipt)">
        <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} disabled={done || previewed !== null} />
      </Field>
      {previewed && <ImplicationPanel implication={previewed.implication} />}
      <ControlOutcome state={state} />
    </DialogFrame>
  );
}

function ImplicationPanel({ implication }: { implication: Implication | null }) {
  if (!implication) return <p className="text-xs text-muted" data-testid="implication">The preview carried no implication.</p>;
  const catchUp = implication.catchUp;
  const tone = catchUp === true ? "bg-amber-dim border-amber/40 text-amber" : catchUp === false ? "bg-green-dim border-green/30 text-green" : "bg-surface-2 border-border text-text-2";
  const headline = catchUp === true ? "Catch-up WILL fire: enabling starts the service immediately." : catchUp === false ? "No catch-up: the next run waits for its schedule." : "Catch-up unknown: assume it may fire immediately.";
  return (
    <div className={`border rounded p-3 text-xs ${tone}`} data-testid="implication" data-catch-up={String(catchUp)}>
      <p className="font-medium">{headline}</p>
      {implication.message && <p className="mt-1 text-text-2">{implication.message}</p>}
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-text-2">
        <dt className="text-muted">persistent</dt><dd>{implication.persistent === null || implication.persistent === undefined ? "—" : String(implication.persistent)}</dd>
        <dt className="text-muted">last trigger</dt><dd>{formatUtc(implication.lastTriggerAt) ?? "—"}</dd>
        <dt className="text-muted">missed elapse</dt><dd>{formatUtc(implication.missedElapseAt) ?? "—"}</dd>
        <dt className="text-muted">next elapse</dt><dd>{formatUtc(implication.nextElapseAt) ?? "—"}{implication.approximate ? " (approximate)" : ""}</dd>
      </dl>
    </div>
  );
}
