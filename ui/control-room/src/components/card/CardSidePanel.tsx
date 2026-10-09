import type { ReactNode } from "react";
import type { CardDetail } from "@/api/schemas/board";
import { inputClass } from "@/components/dialogs/DialogFrame";
import { FIELD_LABELS } from "@/model/card";
import { type Draft, type Editing, lockReason } from "@/model/cardDraft";
import LockNote from "./LockNote";

const label = "block text-text-2 mb-1";
const valueClass = "text-xs text-text";
const PRIORITIES = ["high", "normal", "low"];

interface FieldProps {
  card: CardDetail;
  name: keyof Draft;
  editing?: Editing;
  hint?: string;
  mono?: boolean;
  children: ReactNode;
}

function Control({ name, editing }: { name: keyof Draft; editing: Editing }) {
  const common = { "aria-label": FIELD_LABELS[name] ?? name, value: editing.draft[name], className: inputClass };
  const on = (e: { target: { value: string } }) => editing.set(name, e.target.value);
  if (name === "priority") {
    return (
      <select {...common} onChange={on}>
        {PRIORITIES.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
    );
  }
  const type = name === "research_on" || name === "deadline" ? "date" : "text";
  return <input {...common} type={type} onChange={on} placeholder={type === "text" ? "comma separated" : undefined} />;
}

function SideField({ card, name, editing, hint, mono = false, children }: FieldProps) {
  const open = card.editable.includes(name);
  return (
    <div data-field={name} data-editable={open}>
      <span className={label}>{FIELD_LABELS[name] ?? name}</span>
      {editing && open ? <Control name={name} editing={editing} /> : <div className={`${valueClass} ${mono ? "font-mono" : ""}`}>{children}</div>}
      {hint && <span className="block text-[11px] text-muted mt-1">{hint}</span>}
      {editing && <LockNote name={name} reason={lockReason(card, name)} />}
    </div>
  );
}

const none = <span className="text-muted">none</span>;

export default function CardSidePanel({ card, editing, footer }: { card: CardDetail; editing?: Editing; footer?: ReactNode }) {
  const { fields } = card;
  const shared = { card, editing };
  return (
    <aside className="flex flex-col gap-3 text-xs" aria-label="Card details">
      <SideField {...shared} name="research_on" hint="Not before this morning's run">
        {fields.research_on ?? none}
      </SideField>
      <SideField {...shared} name="deadline">
        {fields.deadline ?? none}
      </SideField>
      <SideField {...shared} name="priority">
        {fields.priority ?? "normal"}
      </SideField>
      <SideField {...shared} name="tags">
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
      <SideField {...shared} name="scope" mono hint="Until the first run; re-briefs">
        {fields.scope.join(", ")}
      </SideField>
      {footer}
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
