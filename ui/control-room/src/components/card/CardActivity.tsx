import type { CardDetail } from "@/api/schemas/board";
import RouteLink from "@/components/RouteLink";
import { activityText, formatDay } from "@/model/card";

export default function CardActivity({ card }: { card: CardDetail }) {
  return (
    <section>
      <div className="text-[13px] font-medium text-text mb-1.5">Activity</div>
      <ul data-testid="activity" className="flex flex-col gap-1 text-xs text-text-2">
        {card.activity.map((row, index) => (
          <li key={`${row.ts}-${index}`}>
            <span className="text-muted mr-1.5">{formatDay(row.ts) ?? "—"}</span>
            {activityText(row)}
            {row.kind === "picked" && row.runId && (
              <>
                {" "}
                <RouteLink to={{ name: "run", id: row.runId }} className="text-accent hover:underline font-mono">
                  receipt
                </RouteLink>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
