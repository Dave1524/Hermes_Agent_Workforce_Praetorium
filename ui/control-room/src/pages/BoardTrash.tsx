import { useState } from "react";
import { type TrashItem, trashResponseSchema } from "@/api/schemas/board";
import { restoreCard } from "@/components/card/cardWriter";
import { buttonClass } from "@/components/dialogs/DialogFrame";
import DataStatusStrip from "@/components/DataStatusStrip";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import { formatDay } from "@/model/card";
import { usePageResource } from "@/shell/usePageResource";

function TrashRow({ item, onRestored }: { item: TrashItem; onRestored: () => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const restore = async () => {
    setBusy(true);
    setProblem(null);
    const result = await restoreCard(item.id);
    setBusy(false);
    if (!result.ok) return setProblem(result.message);
    onRestored();
  };
  return (
    <li data-testid="trash-row" className="flex flex-wrap items-center gap-3 bg-surface-2 border border-border rounded px-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="text-sm text-text break-words">{item.title}</div>
        <div className="text-[11px] text-muted">
          <span className="font-mono">{item.id}</span>
          {item.deletedAt && ` · deleted ${formatDay(item.deletedAt)}`}
          {item.purgeAfter && ` · purged after ${formatDay(item.purgeAfter)}`}
        </div>
        {problem && (
          <div role="alert" className="mt-1 text-xs text-red">
            {problem}
          </div>
        )}
      </div>
      <button type="button" disabled={busy} onClick={() => void restore()} className={buttonClass.secondary}>
        Restore
      </button>
    </li>
  );
}

export default function BoardTrash() {
  const trash = usePageResource("/api/v1/board/trash", trashResponseSchema);
  if (trash.status === "error" && trash.error) return <ErrorNotice what="the trash" error={trash.error} onRetry={trash.refresh} />;
  if (!trash.data) return <Loading what="the trash" />;
  const items = trash.data.items;
  return (
    <>
      <DataStatusStrip status={trash.data.dataStatus} />
      <div className="p-6 max-w-3xl">
        <div className="flex items-center justify-between gap-3 mb-4">
          <p className="text-xs text-muted">Deleted cards stay here for 30 days. Restore is a signed decision; the card returns to the column its history derives.</p>
          <RouteLink to={{ name: "board" }} className="shrink-0 text-xs text-accent hover:underline">
            Back to the board
          </RouteLink>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted">The trash is empty.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {items.map((item) => (
              <TrashRow key={item.id} item={item} onRestored={() => void trash.refresh()} />
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
