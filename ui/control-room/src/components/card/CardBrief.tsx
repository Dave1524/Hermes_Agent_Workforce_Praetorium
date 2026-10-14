import type { CardDetail } from "@/api/schemas/board";
import { buttonClass, inputClass } from "@/components/dialogs/DialogFrame";
import { briefProvenance, latestQuestions } from "@/model/card";
import { type Editing, lockReason } from "@/model/cardDraft";
import LockNote from "./LockNote";

interface Props {
  card: CardDetail;
  editing?: Editing;
  canSave?: boolean;
  onSave?: () => void;
  canSaveAndApprove?: boolean;
  onSaveAndApprove?: () => void;
}

export default function CardBrief({ card, editing, canSave = false, onSave, canSaveAndApprove = false, onSaveAndApprove }: Props) {
  const { brief } = card;
  const editable = card.editable.includes("brief");
  const writable = editing !== undefined && editable;
  const text = writable ? editing.draft.brief : (brief?.text ?? "");
  const asked = card.awaitingAnswer ? latestQuestions(card.activity) : null;
  return (
    <section>
      {card.awaitingAnswer && (
        <div data-testid="brief-questions" className="mb-2 rounded border border-amber/40 bg-amber/10 px-3 py-2 text-xs text-text">
          <div className="font-medium text-amber mb-1">questions for you</div>
          {asked?.detail ? <p className="whitespace-pre-wrap">{asked.detail}</p> : <p className="text-muted">The agent asked before writing the brief; see the activity.</p>}
          <p className="mt-1 text-muted">Answer with a note; the agent then writes the next brief.</p>
        </div>
      )}
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
          {onSaveAndApprove && card.moves.includes("approve_brief") && (
            <button type="button" disabled={!canSaveAndApprove} onClick={onSaveAndApprove} className={buttonClass.secondary}>
              Save and approve
            </button>
          )}
          <span className="text-[11px] text-muted">{card.id === "" ? "Your rough brief is version 1; the agent asks or refines it" : "A changed brief goes back to Refine"}</span>
        </div>
      )}
      {editing && <LockNote name="brief" reason={lockReason(card, "brief")} />}
    </section>
  );
}
