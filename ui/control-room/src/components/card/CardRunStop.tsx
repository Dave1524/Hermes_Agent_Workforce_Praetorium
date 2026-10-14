import { useState } from "react";
import { buttonClass, inputClass } from "@/components/dialogs/DialogFrame";
import { useControlAction, type ControlState } from "@/components/dialogs/useControlAction";

interface Props {
  unit: string;
  onStopped: () => void;
}

const problemOf = (state: ControlState): string | null => {
  if (state.phase === "refused") return state.refusal.message ?? state.refusal.code;
  if (state.phase === "failed") return state.message;
  return null;
};

export default function CardRunStop({ unit, onStopped }: Props) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const { state, send, reset } = useControlAction(unit);
  const problem = problemOf(state);
  const stop = async () => {
    const next = await send({ action: "stop", reason });
    if (next.phase === "applied") onStopped();
  };
  const cancel = () => {
    setAsking(false);
    setReason("");
    reset();
  };
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-border px-3 py-2 text-sm">
      <span className="mr-auto">Running: <span className="font-mono">{unit}</span></span>
      {asking ? (
        <>
          <input aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" className={inputClass} />
          <button type="button" className={buttonClass.danger} disabled={state.phase === "busy" || !reason.trim()} onClick={stop}>Confirm stop</button>
          <button type="button" className={buttonClass.secondary} onClick={cancel}>Cancel</button>
        </>
      ) : (
        <button type="button" className={buttonClass.danger} onClick={() => setAsking(true)}>Stop run</button>
      )}
      {problem && <p role="alert" className="w-full text-red">{problem}</p>}
    </div>
  );
}
