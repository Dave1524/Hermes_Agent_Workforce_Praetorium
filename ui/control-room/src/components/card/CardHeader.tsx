import type { CardDetail } from "@/api/schemas/board";
import { inputClass } from "@/components/dialogs/DialogFrame";
import { formatDay } from "@/model/card";
import { type Editing, lockReason } from "@/model/cardDraft";
import LockNote from "./LockNote";

const chip = "px-2 py-0.5 rounded text-xs";

function Title({ card, editing }: { card: CardDetail; editing?: Editing }) {
  const open = card.editable.includes("title");
  if (editing && open) {
    return (
      <input
        aria-label="Title"
        data-field="title"
        data-editable="true"
        placeholder="Title"
        value={editing.draft.title}
        onChange={(e) => editing.set("title", e.target.value)}
        className={`${inputClass} text-base font-medium`}
      />
    );
  }
  return (
    <h3 data-field="title" data-editable={open} className="text-base font-medium text-text break-words">
      {card.fields.title}
    </h3>
  );
}

export default function CardHeader({ card, editing }: { card: CardDetail; editing?: Editing }) {
  const schedule = card.scheduled ? formatDay(card.researchOn) : null;
  return (
    <div className="min-w-0 flex-1">
      <Title card={card} editing={editing} />
      {editing && <LockNote name="title" reason={lockReason(card, "title")} />}
      <div className="flex gap-2 items-center flex-wrap mt-2">
        <span data-testid="card-column" className={`${chip} bg-accent-dim text-accent`}>
          {card.id === "" ? "New card, starts in Backlog" : card.column}
        </span>
        {card.outcome && (
          <span data-testid="card-outcome" className={`${chip} bg-surface-2 text-text-2`}>
            {card.outcome}
          </span>
        )}
        {card.blockedCause && (
          <span data-testid="card-blocked" className={`${chip} bg-red-dim text-red`}>
            Blocked: {card.blockedCause}
          </span>
        )}
        {card.approvedLanding && (
          <span data-testid="card-landing" className={`${chip} bg-green-dim text-green`}>
            approved, lands within the hour
          </span>
        )}
        {schedule && (
          <span data-testid="card-scheduled" className={`${chip} bg-surface-2 text-text-2`}>
            Scheduled {schedule}
          </span>
        )}
        {card.id !== "" && <span className="font-mono text-xs text-muted">{card.id}</span>}
      </div>
    </div>
  );
}
