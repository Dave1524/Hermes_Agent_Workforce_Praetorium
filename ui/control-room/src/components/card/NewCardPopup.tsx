import { useMemo } from "react";
import CardDialog from "@/components/dialogs/CardDialog";
import { emptyCard } from "@/model/cardDraft";
import { navigate } from "@/router/useRoute";
import { cardWriter } from "./cardWriter";

const close = () => navigate({ name: "board" });

export default function NewCardPopup() {
  const card = useMemo(emptyCard, []);
  const writer = useMemo(() => cardWriter(""), []);
  const created = (id: string | null) => navigate(id ? { name: "card", id } : { name: "board" });
  return <CardDialog card={card} onClose={close} writer={writer} onChanged={created} />;
}
