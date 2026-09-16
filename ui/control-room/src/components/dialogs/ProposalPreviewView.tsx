import type { z } from "zod";
import type { proposalPreviewSchema, residueReportSchema } from "@/api/schemas/proposals";
import { formatUtc } from "@/model/time";

type ProposalPreview = z.infer<typeof proposalPreviewSchema>;
type ResidueReport = z.infer<typeof residueReportSchema>;

const CHECK_TONE: Record<string, string> = { pass: "text-green", fail: "text-red", skip: "text-muted", skipped: "text-muted" };

export default function ProposalPreviewView({ preview }: { preview: ProposalPreview }) {
  return (
    <div className="space-y-3" data-testid="proposal-preview">
      <div className="bg-surface-2 border border-border rounded p-3 text-xs space-y-1">
        {preview.summary && <p className="text-text font-medium">{preview.summary}</p>}
        <p className="font-mono text-muted">
          {preview.branch ?? "—"} → {preview.base ?? "—"}
          {preview.expires_at && <> · preview valid until {formatUtc(preview.expires_at) ?? preview.expires_at}</>}
        </p>
        {preview.description && Object.keys(preview.description).length > 0 && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono mt-1">
            {Object.entries(preview.description).map(([k, v]) => (
              <Description key={k} name={k} value={v} />
            ))}
          </dl>
        )}
      </div>
      {preview.files.length > 0 && (
        <p className="text-xs font-mono text-text-2">
          {preview.files.length} file{preview.files.length === 1 ? "" : "s"}: {preview.files.join(", ")}
        </p>
      )}
      {preview.diff && (
        <details>
          <summary className="cursor-pointer text-xs text-text-2">diff{preview.diff_sha256 ? ` · ${preview.diff_sha256.slice(0, 12)}` : ""}</summary>
          <pre className="mt-1 max-h-64 overflow-auto bg-bg border border-border rounded p-2 font-mono text-[11px] text-text-2 whitespace-pre">{preview.diff}</pre>
        </details>
      )}
      {preview.checks.length > 0 && (
        <ul className="text-xs space-y-1" data-testid="checks">
          {preview.checks.map((c) => (
            <li key={c.id} className="flex gap-2 items-baseline">
              <span className={`font-mono w-10 shrink-0 ${CHECK_TONE[c.status] ?? "text-amber"}`}>{c.status}</span>
              <span className="font-mono text-text">{c.id}</span>
              {c.class && <span className="text-muted">({c.class})</span>}
              {c.status === "fail" && c.output && <span className="text-text-2 truncate" title={c.output}>{c.output}</span>}
            </li>
          ))}
        </ul>
      )}
      {preview.residue?.live && <ResiduePanel report={preview.residue.live} />}
      {preview.submit_blockers.length > 0 && (
        <ul className="text-xs text-amber space-y-0.5" data-testid="blockers">
          {preview.submit_blockers.map((b) => <li key={b}>{b}</li>)}
        </ul>
      )}
    </div>
  );
}

function Description({ name, value }: { name: string; value: unknown }) {
  const text = Array.isArray(value) ? value.map(String).join(" | ") : value === null || value === undefined ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value);
  return (
    <>
      <dt className="text-muted">{name}</dt>
      <dd className="text-text-2 break-all">{text}</dd>
    </>
  );
}

function ResiduePanel({ report }: { report: ResidueReport }) {
  return (
    <div className="text-xs" data-testid="residue">
      <p className="text-text-2">
        Live residue: <span className="font-mono text-text">{report.verdict ?? "unknown"}</span>
      </p>
      {report.items.length > 0 && (
        <ul className="mt-1 space-y-0.5 font-mono text-muted">
          {report.items.map((item, i) => (
            <li key={i}>
              {item.class ?? "?"} · {item.what ?? item.path ?? "—"}
              {item.how ? ` — ${item.how}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
