import type { CardDetail } from "@/api/schemas/board";
import { inputClass } from "@/components/dialogs/DialogFrame";
import { type Editing, lockReason } from "@/model/cardDraft";
import LockNote from "./LockNote";

export default function CardIdea({ card, editing }: { card: CardDetail; editing?: Editing }) {
  const open = card.editable.includes("idea");
  const writable = editing !== undefined && open;
  return (
    <section>
      <div className="text-[13px] font-medium text-text mb-1.5">Idea</div>
      <textarea
        readOnly={!writable}
        rows={2}
        aria-label="Idea"
        data-field="idea"
        data-editable={open}
        value={writable ? editing.draft.idea : card.fields.idea}
        onChange={writable ? (e) => editing.set("idea", e.target.value) : undefined}
        className={`${inputClass} resize-y`}
      />
      {editing && <LockNote name="idea" reason={lockReason(card, "idea")} />}
    </section>
  );
}
