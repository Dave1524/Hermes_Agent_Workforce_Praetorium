import type { LastAction } from "@/api/schemas/workflow";
import { formatUtc } from "@/model/time";
import { Row } from "./Panel";

const RESULT_TONE: Record<string, string> = { applied: "text-green", previewed: "text-blue", refused: "text-amber", failed: "text-red" };

// The newest non-preview receipt, as the API summarises it (before/after are states, not units).
export default function LastActionPanel({ lastAction }: { lastAction: LastAction | null }) {
  if (!lastAction) return <p className="text-xs text-muted">No control action recorded.</p>;
  const result = lastAction.result ?? "unknown";
  return (
    <div className="bg-surface-2 border border-border rounded p-3 text-xs" data-testid="last-action" data-result={result}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`font-mono font-semibold ${RESULT_TONE[result] ?? "text-muted"}`}>{result}</span>
        {lastAction.action && <span className="font-mono text-text-2">{lastAction.action}</span>}
        {lastAction.receiptId && <span className="font-mono text-muted ml-auto">{lastAction.receiptId}</span>}
      </div>
      {lastAction.refusal && <p className="text-amber font-mono mb-2">{lastAction.refusal}</p>}
      <Row label="Before → after">{lastAction.before ?? "—"} → {lastAction.after ?? "—"}</Row>
      {lastAction.actor && <Row label="Actor">{lastAction.actor}</Row>}
      {lastAction.reason && <Row label="Reason">{lastAction.reason}</Row>}
      {lastAction.at && <Row label="At">{formatUtc(lastAction.at) ?? lastAction.at}</Row>}
      {lastAction.note && <p className="text-text-2 mt-2">{lastAction.note}</p>}
    </div>
  );
}
