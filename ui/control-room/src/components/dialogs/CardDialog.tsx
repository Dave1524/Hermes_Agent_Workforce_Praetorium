import type { CardDetail } from "@/api/schemas/board";
import CardActivity from "@/components/card/CardActivity";
import CardBrief from "@/components/card/CardBrief";
import CardEditActions from "@/components/card/CardEditActions";
import CardFooter from "@/components/card/CardFooter";
import CardHeader from "@/components/card/CardHeader";
import CardIdea from "@/components/card/CardIdea";
import CardNote from "@/components/card/CardNote";
import CardResearch from "@/components/card/CardResearch";
import CardSidePanel from "@/components/card/CardSidePanel";
import type { CardWriter } from "@/components/card/cardWriter";
import { useCardEdit } from "@/components/card/useCardEdit";
import DialogFrame from "./DialogFrame";

export interface CardDialogProps {
  card: CardDetail;
  onClose: () => void;
  writer?: CardWriter;
  onChanged?: (created: string | null) => void;
  onReload?: () => void;
}

const DISCARD = "Discard your unsaved edits?";

function EditableCardDialog({ card, onClose, writer, onChanged, onReload }: CardDialogProps & { writer: CardWriter }) {
  const edit = useCardEdit(card, writer, onChanged ?? (() => undefined));
  const guarded = () => {
    if (!edit.dirty || window.confirm(DISCARD)) onClose();
  };
  const { editing } = edit;
  return (
    <DialogFrame
      wide
      title={card.fields.title || "New card"}
      header={<CardHeader card={card} editing={editing} />}
      onClose={guarded}
      footer={<CardFooter moves={card.moves} creating={edit.creating} canCreate={edit.canCreate} onCreate={edit.create} />}
    >
      <CardEditActions problem={edit.problem} onReload={onReload} />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_190px]">
        <div className="min-w-0 flex flex-col gap-3.5">
          <CardBrief card={card} editing={editing} canSave={edit.canSaveBrief} onSave={edit.creating ? undefined : edit.saveBrief} />
          <CardIdea card={card} editing={editing} />
          <CardResearch research={card.research} />
          {!edit.creating && <CardActivity card={card} />}
          {!edit.creating && <CardNote editing={editing} canAdd={edit.canAddNote} onAdd={edit.addNote} />}
        </div>
        <CardSidePanel card={card} editing={editing} footer={edit.creating ? undefined : <CardEditActions.Save disabled={!edit.canSaveDetails} onClick={edit.saveDetails} />} />
      </div>
    </DialogFrame>
  );
}

export default function CardDialog(props: CardDialogProps) {
  const { card, onClose, writer } = props;
  if (writer) return <EditableCardDialog {...props} writer={writer} />;
  return (
    <DialogFrame wide title={card.fields.title} header={<CardHeader card={card} />} onClose={onClose} footer={<CardFooter moves={card.moves} />}>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_190px]">
        <div className="min-w-0 flex flex-col gap-3.5">
          <CardBrief card={card} />
          <CardIdea card={card} />
          <CardResearch research={card.research} />
          <CardActivity card={card} />
        </div>
        <CardSidePanel card={card} />
      </div>
    </DialogFrame>
  );
}
