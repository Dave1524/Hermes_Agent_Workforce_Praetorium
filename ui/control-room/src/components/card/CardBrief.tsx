import type { CardDetail } from "@/api/schemas/board";
import { buttonClass, inputClass } from "@/components/dialogs/DialogFrame";
import { briefProvenance } from "@/model/card";
import { type Editing, lockReason } from "@/model/cardDraft";
import LockNote from "./LockNote";

interface Props {
  card: CardDetail;
  editing?: Editing;
  canSave?: boolean;
  onSave?: () => void;
}

export default function CardBrief({ card, editing, canSave = false, onSave }: Props) {
  const { brief } = card;
  const editable = card.editable.includes("brief");
  const writable = editing !== undefined && editable;
  const text = writable ? editing.draft.brief : (brief?.text ?? "");
  return (
    <section>
      <div className="flex justify-between items-baseline gap-2 mb-1.5">
        <span className="text-[13px] font-medium text-text">Brief</span>
        {brief && (
          <span data-testid="brief-provenance" className={`text-xs ${brief.approved ? "text-green" : "text-text-2"}`}>
            {briefProvenance(brief)}
            {!brief.current && " (not current)"}
          </span>
        )}
      </div>
      {text || writable ? (
        <textarea
          readOnly={!writable}
          rows={8}
          aria-label="Brief"
          data-field="brief"
          data-editable={editable}
          value={text}
          onChange={writable ? (e) => editing.set("brief", e.target.value) : undefined}
          className={`${inputClass} font-mono text-xs resize-y leading-normal`}
        />
      ) : (
        <p data-field="brief" data-editable={editable} className="text-xs text-muted">
          No brief yet.
        </p>
      )}
      {writable && onSave && (
        <div className="mt-1.5 flex items-center gap-2">
          <button type="button" disabled={!canSave} onClick={onSave} className={buttonClass.primary}>
            Save brief
          </button>
          <span className="text-[11px] text-muted">A changed brief goes back to Refine</span>
        </div>
      )}
      {editing && <LockNote name="brief" reason={lockReason(card, "brief")} />}
    </section>
  );
}
