import { buttonClass } from "@/components/dialogs/DialogFrame";
import { moveLabel } from "@/model/card";

const DANGER = new Set(["withdraw", "reject"]);
const WAITING = "Decisions arrive with the broker; the board only reads for now.";

export default function CardFooter({ moves }: { moves: string[] }) {
  return (
    <>
      <span className="mr-auto text-xs text-muted">Moves by decision only</span>
      {moves.map((move) => (
        <button key={move} type="button" disabled title={WAITING} data-move={move} className={DANGER.has(move) ? buttonClass.danger : buttonClass.secondary}>
          {moveLabel(move)}
        </button>
      ))}
    </>
  );
}
