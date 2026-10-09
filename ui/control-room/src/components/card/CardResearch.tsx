import type { CardResearch as Research } from "@/api/schemas/board";

const VERDICT_TONE: Record<string, string> = { MET: "text-green", PARTLY: "text-amber", "NOT MET": "text-red" };

export default function CardResearch({ research }: { research: Research }) {
  if (research.status === "none") return null;
  return (
    <section data-testid="card-research">
      <div className="flex justify-between items-baseline gap-2 mb-1.5">
        <span className="text-[13px] font-medium text-text">Research</span>
        <span className="flex gap-3 text-xs">
          {research.changed && (
            <span data-testid="page-changed" className="text-amber">
              edited since it was published
            </span>
          )}
          {research.url && (
            <a href={research.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Open in Notion
            </a>
          )}
        </span>
      </div>
      {research.status === "unavailable" ? (
        <p role="status" className="text-xs text-amber">
          The page could not be read: {research.reason ?? "unknown error"}
        </p>
      ) : (
        <>
          <ul data-testid="acceptance" className="space-y-1 mb-2">
            {research.acceptance.map((row) => (
              <li key={row.line} className="text-xs flex gap-2">
                <span className={`font-mono w-14 shrink-0 ${VERDICT_TONE[row.answer ?? ""] ?? "text-muted"}`}>{row.answer ?? "no answer"}</span>
                <span className="text-text-2">{row.line}</span>
              </li>
            ))}
          </ul>
          <pre className="text-[11px] font-mono text-text-2 bg-surface-2 border border-border rounded p-3 max-h-64 overflow-auto whitespace-pre-wrap">{research.text}</pre>
        </>
      )}
    </section>
  );
}
