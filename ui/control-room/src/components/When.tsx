import { formatUtc, relativeTime } from "@/model/time";

export default function When({ iso, estimated = false, empty = "—" }: { iso: string | null | undefined; estimated?: boolean; empty?: string }) {
  const rel = relativeTime(iso);
  if (rel === null) return <span className="font-mono text-xs text-muted">{empty}</span>;
  return (
    <time dateTime={iso ?? undefined} title={formatUtc(iso) ?? undefined} className="font-mono text-xs text-text-2">
      {estimated ? "~" : ""}
      {rel}
    </time>
  );
}
