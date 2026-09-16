import type { ApiError } from "@/api/client";

export function Loading({ what }: { what: string }) {
  return (
    <div className="p-6 text-sm text-muted font-mono" role="status">
      Loading {what}…
    </div>
  );
}

const describe = (error: ApiError): string => {
  if (error.status === 0) return error.message;
  const body = error.body;
  if (body && typeof body === "object" && "error" in body && typeof body.error === "string") return `${error.status}: ${body.error}`;
  return `HTTP ${error.status}`;
};

export function ErrorNotice({ what, error, onRetry }: { what: string; error: ApiError; onRetry?: () => void }) {
  return (
    <div className="m-6 bg-red-dim border border-red/30 rounded-md p-4 text-sm" role="alert">
      <div className="text-red font-medium">Could not load {what}</div>
      <div className="text-text-2 font-mono text-xs mt-1">{describe(error)}</div>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 px-2.5 py-1 text-xs border border-border rounded text-text-2 hover:bg-surface-3 transition-colors">
          Retry
        </button>
      )}
    </div>
  );
}
