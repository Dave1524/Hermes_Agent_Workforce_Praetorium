import type { CardDetail } from "@/api/schemas/board";
import { inputClass } from "@/components/dialogs/DialogFrame";

export default function CardIdea({ card }: { card: CardDetail }) {
  return (
    <section>
      <div className="text-[13px] font-medium text-text mb-1.5">Idea</div>
      <textarea
        readOnly
        rows={2}
        aria-label="Idea"
        data-field="idea"
        data-editable={card.editable.includes("idea")}
        value={card.fields.idea}
        className={`${inputClass} resize-y`}
      />
    </section>
  );
}
