import type { ReactNode } from "react";
import type { CardDetail } from "@/api/schemas/board";
import { FIELD_LABELS } from "@/model/card";

const label = "block text-text-2 mb-1";
const valueClass = "text-xs text-text";

function SideField({ card, name, hint, mono = false, children }: { card: CardDetail; name: string; hint?: string; mono?: boolean; children: ReactNode }) {
  return (
    <div data-field={name} data-editable={card.editable.includes(name)}>
      <span className={label}>{FIELD_LABELS[name] ?? name}</span>
      <div className={`${valueClass} ${mono ? "font-mono" : ""}`}>{children}</div>
      {hint && <span className="block text-[11px] text-muted mt-1">{hint}</span>}
    </div>
  );
}

const none = <span className="text-muted">none</span>;

export default function CardSidePanel({ card }: { card: CardDetail }) {
  const { fields } = card;
  return (
    <aside className="flex flex-col gap-3 text-xs" aria-label="Card details">
      <SideField card={card} name="research_on" hint="Not before this morning's run">
        {fields.research_on ?? none}
      </SideField>
      <SideField card={card} name="deadline">
        {fields.deadline ?? none}
      </SideField>
      <SideField card={card} name="priority">
        {fields.priority ?? "normal"}
      </SideField>
      <SideField card={card} name="tags">
        {fields.tags.length === 0 ? none : (
          <span className="flex gap-1.5 flex-wrap">
            {fields.tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 rounded bg-surface-2 text-text-2">
                {tag}
              </span>
            ))}
          </span>
        )}
      </SideField>
      <SideField card={card} name="scope" mono hint="Until the first run; re-briefs">
        {fields.scope.join(", ")}
      </SideField>
      <div className="border-t border-border pt-2 text-text-2 space-y-1">
        <div className="flex justify-between" data-field="owner" data-editable="false">
          <span>Owner</span>
          <span className="capitalize">{card.owner}</span>
        </div>
        <div className="flex justify-between" data-field="kind" data-editable="false">
          <span>Kind</span>
          <span className="capitalize">{card.kind}</span>
        </div>
      </div>
    </aside>
  );
}
