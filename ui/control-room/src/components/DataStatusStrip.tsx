import type { DataStatus } from "@/api/schemas/dataStatus";

const TONE: Record<string, string> = {
  available: "text-green",
  degraded: "text-amber",
  unavailable: "text-red",
};

const entries = (status: DataStatus): Array<[string, string]> =>
  Object.entries(status).flatMap(([k, v]) => (k !== "errors" && typeof v === "string" ? [[k, v] as [string, string]] : []));

const errorLines = (status: DataStatus): string[] =>
  Object.entries(status.errors ?? {}).flatMap(([k, v]) => (Array.isArray(v) ? v.map((e) => `${k}: ${String(e)}`) : v ? [`${k}: ${String(v)}`] : []));

export default function DataStatusStrip({ status }: { status: DataStatus }) {
  const sources = entries(status);
  const errors = errorLines(status);
  if (sources.every(([, v]) => v === "available") && errors.length === 0) return null;
  return (
    <div className="mx-6 mt-4 bg-surface-2 border border-border rounded-md px-4 py-2 text-xs" data-testid="data-status">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono">
        {sources.map(([k, v]) => (
          <span key={k}>
            <span className="text-muted">{k}</span> <span className={TONE[v] ?? "text-text-2"}>{v}</span>
          </span>
        ))}
      </div>
      {errors.length > 0 && (
        <ul className="mt-1 text-text-2 space-y-0.5">
          {errors.map((line) => (
            <li key={line} className="font-mono break-all">
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
