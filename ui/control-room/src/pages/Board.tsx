import { boardResponseSchema, type CardSummary } from "@/api/schemas/board";
import CardPopup from "@/components/card/CardPopup";
import NewCardPopup from "@/components/card/NewCardPopup";
import DataStatusStrip from "@/components/DataStatusStrip";
import { ErrorNotice, Loading } from "@/components/ResourceState";
import RouteLink from "@/components/RouteLink";
import { formatDay } from "@/model/card";
import { usePageResource } from "@/shell/usePageResource";

function BoardCard({ card }: { card: CardSummary }) {
  const scheduled = card.scheduled ? formatDay(card.researchOn) : null;
  return (
    <RouteLink
      to={{ name: "card", id: card.id }}
      data-testid="board-card"
      className="block bg-surface-2 border border-border rounded px-3 py-2 hover:border-border-2 transition-colors"
    >
      <div className="text-sm text-text break-words">{card.title}</div>
      <div className="flex flex-wrap gap-1.5 mt-1.5 text-[11px]">
        {card.priority && card.priority !== "normal" && <span className="text-accent">{card.priority}</span>}
        {scheduled && <span className="text-text-2">Scheduled {scheduled}</span>}
        {card.blockedCause && <span className="text-red">{card.blockedCause}</span>}
        {card.approvedLanding && <span className="text-green">approved, landing</span>}
        {card.outcome && <span className="text-text-2">{card.outcome}</span>}
        {card.exceptions.length > 0 && <span className="text-amber">{card.exceptions.join(", ")}</span>}
        <span className="font-mono text-muted">{card.owner}</span>
      </div>
    </RouteLink>
  );
}

export default function Board({ cardId, creating = false }: { cardId?: string; creating?: boolean }) {
  const board = usePageResource("/api/v1/board", boardResponseSchema);
  if (board.status === "error" && board.error) return <ErrorNotice what="the board" error={board.error} onRetry={board.refresh} />;
  if (!board.data) return <Loading what="the board" />;
  const { columns, cards } = board.data.items;
  return (
    <>
      <DataStatusStrip status={board.data.dataStatus} />
      <div className="p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <p className="text-xs text-muted">Each column is derived from the card's events, decisions and receipts. Open a card to read or edit it; a card moves only by decision.</p>
          <RouteLink to={{ name: "newcard" }} className="shrink-0 px-3 py-1.5 text-xs font-medium bg-accent-dim border border-accent/30 text-accent rounded hover:bg-accent/20">
            New card
          </RouteLink>
        </div>
        <div className="grid gap-3 overflow-x-auto" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(190px, 1fr))` }}>
          {columns.map((column) => {
            const inColumn = cards.filter((c) => c.column === column);
            return (
              <section key={column} data-testid="board-column" data-column={column} className="bg-surface border border-border rounded-md p-3 min-h-32">
                <h2 className="flex items-center gap-2 text-xs font-semibold text-text uppercase tracking-wider mb-3">
                  {column}
                  <span className="font-mono text-text-2 bg-surface-3 rounded-full px-1.5 py-0.5">{inColumn.length}</span>
                </h2>
                <div className="flex flex-col gap-2">
                  {inColumn.map((card) => (
                    <BoardCard key={card.id} card={card} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
      {cardId !== undefined && <CardPopup cardId={cardId} />}
      {creating && <NewCardPopup />}
    </>
  );
}
