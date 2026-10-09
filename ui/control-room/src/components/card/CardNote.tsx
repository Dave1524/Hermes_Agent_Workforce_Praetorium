import { buttonClass, inputClass } from "@/components/dialogs/DialogFrame";
import type { Editing } from "@/model/cardDraft";

export default function CardNote({ editing, canAdd, onAdd }: { editing: Editing; canAdd: boolean; onAdd: () => void }) {
  return (
    <div className="flex gap-2 items-start">
      <input
        aria-label="Add a note"
        placeholder="Add a note"
        value={editing.draft.note}
        onChange={(e) => editing.set("note", e.target.value)}
        className={inputClass}
      />
      <button type="button" disabled={!canAdd} onClick={onAdd} className={buttonClass.secondary}>
        Add
      </button>
    </div>
  );
}
