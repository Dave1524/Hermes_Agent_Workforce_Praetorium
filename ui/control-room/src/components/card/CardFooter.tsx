import { buttonClass, inputClass } from "@/components/dialogs/DialogFrame";
import { moveLabel } from "@/model/card";
import type { CardDecision } from "./useCardDecision";

const DANGER = new Set(["delete", "reject"]);
const READ_ONLY = "This view only reads; open the card from the board to decide.";

interface Props {
  moves: string[];
  creating?: boolean;
  canCreate?: boolean;
  onCreate?: () => void;
  decision?: CardDecision;
}

function ReasonRow({ decision }: { decision: CardDecision }) {
  const { pending, needsReason, reason } = decision;
  if (!pending) return null;
  const label = moveLabel(pending).toLowerCase();
  return (
    <div className="flex flex-1 items-center gap-2">
      <input
        aria-label="Reason"
        value={reason}
        onChange={(e) => decision.setReason(e.target.value)}
        placeholder={needsReason ? "Reason (required)" : "Reason (optional)"}
        className={inputClass}
      />
      <button type="button" disabled={decision.busy || (needsReason && !reason.trim())} onClick={decision.confirm} className={DANGER.has(pending) ? buttonClass.danger : buttonClass.primary}>
        {`Confirm ${label}`}
      </button>
      <button type="button" onClick={decision.cancel} className={buttonClass.secondary}>
        Cancel
      </button>
    </div>
  );
}

export default function CardFooter({ moves, creating = false, canCreate = false, onCreate, decision }: Props) {
  if (creating) {
    return (
      <button type="button" disabled={!canCreate} onClick={onCreate} className={buttonClass.primary}>
        Create card
      </button>
    );
  }
  return (
    <>
      <span className="mr-auto text-xs text-muted">Moves by decision only</span>
      {decision?.pending ? (
        <ReasonRow decision={decision} />
      ) : (
        moves.map((move) => {
          const why = decision ? decision.unavailable(move) : READ_ONLY;
          return (
            <button
              key={move}
              type="button"
              disabled={why !== null}
              title={why ?? undefined}
              data-move={move}
              onClick={() => decision?.choose(move)}
              className={DANGER.has(move) ? buttonClass.danger : buttonClass.secondary}
            >
              {moveLabel(move)}
            </button>
          );
        })
      )}
    </>
  );
}
