import type { CardDetail } from "@/api/schemas/board";
import { briefProvenance } from "@/model/card";
import { inputClass } from "@/components/dialogs/DialogFrame";

export default function CardBrief({ card }: { card: CardDetail }) {
  const { brief } = card;
  const editable = card.editable.includes("brief");
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
      {brief?.text ? (
        <textarea
          readOnly
          rows={8}
          aria-label="Brief"
          data-field="brief"
          data-editable={editable}
          value={brief.text}
          className={`${inputClass} font-mono text-xs resize-y leading-normal`}
        />
      ) : (
        <p data-field="brief" data-editable={editable} className="text-xs text-muted">
          No brief yet.
        </p>
      )}
    </section>
  );
}
