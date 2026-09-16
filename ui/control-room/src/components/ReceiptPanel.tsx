import type { ControlReceipt } from "@/api/schemas/control";
import { formatUtc } from "@/model/time";
import { Row } from "./Panel";

const RESULT_TONE: Record<string, string> = { applied: "text-green", previewed: "text-blue", refused: "text-amber", failed: "text-red" };

const linkEntries = (links: ControlReceipt["links"]): Array<[string, string]> =>
  Object.entries(links ?? {}).flatMap(([k, v]) => (typeof v === "string" && v ? [[k, v] as [string, string]] : []));

export default function ReceiptPanel({ receipt }: { receipt: ControlReceipt }) {
  const result = receipt.result ?? "unknown";
  return (
    <div className="bg-surface-2 border border-border rounded p-3 text-xs" data-testid="receipt" data-result={result}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`font-mono font-semibold ${RESULT_TONE[result] ?? "text-muted"}`}>{result}</span>
        {receipt.action && <span className="font-mono text-text-2">{receipt.action}{receipt.stage ? ` · ${receipt.stage}` : ""}</span>}
        {receipt.receipt_id && <span className="font-mono text-muted ml-auto">{receipt.receipt_id}</span>}
      </div>
      {receipt.refusal && (
        <p className="text-amber font-mono mb-2">
          {receipt.refusal.code}
          {receipt.refusal.message ? ` · ${receipt.refusal.message}` : ""}
        </p>
      )}
      <Row label="Before → after">{receipt.before?.state ?? "—"} → {receipt.after?.state ?? "—"}</Row>
      {receipt.run_id && <Row label="Run">{receipt.run_id}</Row>}
      {receipt.next_scheduled_run && <Row label="Next scheduled run">{formatUtc(receipt.next_scheduled_run) ?? receipt.next_scheduled_run}</Row>}
      {receipt.catch_up_fired !== null && receipt.catch_up_fired !== undefined && <Row label="Catch-up fired">{receipt.catch_up_fired ? "yes" : "no"}</Row>}
      {receipt.trigger && <Row label="Trigger">{receipt.trigger}</Row>}
      {receipt.completed_at && <Row label="Completed">{formatUtc(receipt.completed_at) ?? receipt.completed_at}</Row>}
      {receipt.note && <p className="text-text-2 mt-2">{receipt.note}</p>}
      {linkEntries(receipt.links).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-3">
          {linkEntries(receipt.links).map(([k, v]) => (
            <a key={k} href={v} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline font-mono">
              {k}
            </a>
          ))}
        </div>
      )}
      {receipt.commands && receipt.commands.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-muted">commands ({receipt.commands.length})</summary>
          <pre className="mt-1 font-mono text-[11px] text-text-2 whitespace-pre-wrap break-all">{JSON.stringify(receipt.commands, null, 1)}</pre>
        </details>
      )}
    </div>
  );
}
