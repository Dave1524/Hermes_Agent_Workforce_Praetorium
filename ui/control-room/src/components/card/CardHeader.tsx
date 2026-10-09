import type { CardDetail } from "@/api/schemas/board";
import { formatDay } from "@/model/card";

const chip = "px-2 py-0.5 rounded text-xs";

export default function CardHeader({ card }: { card: CardDetail }) {
  const schedule = card.scheduled ? formatDay(card.researchOn) : null;
  return (
    <div className="min-w-0 flex-1">
      <h3 data-field="title" data-editable={card.editable.includes("title")} className="text-base font-medium text-text break-words">
        {card.fields.title}
      </h3>
      <div className="flex gap-2 items-center flex-wrap mt-2">
        <span data-testid="card-column" className={`${chip} bg-accent-dim text-accent`}>
          {card.column}
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
        <span className="font-mono text-xs text-muted">{card.id}</span>
      </div>
    </div>
  );
}
