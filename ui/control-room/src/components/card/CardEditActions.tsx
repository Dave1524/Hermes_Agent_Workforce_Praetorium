import { buttonClass } from "@/components/dialogs/DialogFrame";
import type { EditProblem } from "./useCardEdit";

const STALE = "This card changed while you were editing, so nothing was saved. Reload to see the current card.";

function Problem({ problem, onReload }: { problem: EditProblem | null; onReload?: () => void }) {
  if (!problem) return null;
  return (
    <div role="alert" className="flex items-center gap-2 rounded border border-red/40 bg-red-dim px-3 py-2 text-xs text-red">
      <span className="flex-1">{problem.stale ? STALE : problem.message}</span>
      {problem.stale && onReload && (
        <button type="button" onClick={onReload} className={buttonClass.secondary}>
          Reload
        </button>
      )}
    </div>
  );
}

function Save({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className={buttonClass.primary}>
      Save details
    </button>
  );
}

const CardEditActions = Object.assign(Problem, { Save });
export default CardEditActions;
