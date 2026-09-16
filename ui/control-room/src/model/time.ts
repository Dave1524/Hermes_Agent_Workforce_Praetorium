const parse = (iso: string | null | undefined): Date | null => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

const units: ReadonlyArray<[label: string, seconds: number]> = [
  ["d", 86_400],
  ["h", 3_600],
  ["m", 60],
  ["s", 1],
];

const coarse = (seconds: number): string => {
  for (const [label, size] of units) {
    if (seconds >= size) return `${Math.floor(seconds / size)}${label}`;
  }
  return "0s";
};

export const relativeTime = (iso: string | null | undefined, now: Date = new Date()): string | null => {
  const d = parse(iso);
  if (!d) return null;
  const delta = Math.round((d.getTime() - now.getTime()) / 1000);
  return delta < 0 ? `${coarse(-delta)} ago` : `in ${coarse(delta)}`;
};

export const formatUtc = (iso: string | null | undefined): string | null => {
  const d = parse(iso);
  if (!d) return null;
  return `${d.toISOString().slice(0, 16).replace("T", " ")}Z`;
};

export const durationSeconds = (start: string | null | undefined, end: string | null | undefined): number | null => {
  const a = parse(start);
  const b = parse(end);
  if (!a || !b) return null;
  return Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000));
};

export const formatDuration = (seconds: number | null | undefined): string | null => {
  if (seconds === null || seconds === undefined) return null;
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
};

export const formatCadence = (seconds: number | null | undefined): string | null => {
  if (seconds === null || seconds === undefined) return null;
  if (seconds % 86_400 === 0) return `every ${seconds / 86_400}d`;
  if (seconds % 3_600 === 0) return `every ${seconds / 3_600}h`;
  if (seconds % 60 === 0) return `every ${seconds / 60}m`;
  return `every ${seconds}s`;
};
