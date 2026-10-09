import type { CardDetail } from "@/api/schemas/board";
import CardActivity from "@/components/card/CardActivity";
import CardBrief from "@/components/card/CardBrief";
import CardFooter from "@/components/card/CardFooter";
import CardHeader from "@/components/card/CardHeader";
import CardIdea from "@/components/card/CardIdea";
import CardResearch from "@/components/card/CardResearch";
import CardSidePanel from "@/components/card/CardSidePanel";
import DialogFrame from "./DialogFrame";

export interface CardDialogProps {
  card: CardDetail;
  onClose: () => void;
}

export default function CardDialog({ card, onClose }: CardDialogProps) {
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
