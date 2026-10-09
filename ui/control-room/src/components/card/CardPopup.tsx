import { cardResponseSchema } from "@/api/schemas/board";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import CardDialog from "@/components/dialogs/CardDialog";
import DialogFrame from "@/components/dialogs/DialogFrame";
import { navigate } from "@/router/useRoute";
import { useSecondaryResource } from "@/shell/usePageResource";

const close = () => navigate({ name: "board" });

export default function CardPopup({ cardId }: { cardId: string }) {
  const resource = useSecondaryResource(`/api/v1/board/${encodeURIComponent(cardId)}`, cardResponseSchema);
  if (resource.status === "error" && resource.error) {
    return (
      <DialogFrame title="Card" onClose={close}>
        <ErrorNotice what={`card ${cardId}`} error={resource.error} onRetry={resource.refresh} />
      </DialogFrame>
    );
  }
  if (!resource.data) {
    return (
      <DialogFrame title="Card" onClose={close}>
        <Loading what={`card ${cardId}`} />
      </DialogFrame>
    );
  }
  return <CardDialog card={resource.data.items} onClose={close} />;
}
