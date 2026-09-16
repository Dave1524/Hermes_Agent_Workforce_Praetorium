export const HEALTHS = ["healthy", "running", "incomplete", "failed", "paused", "unknown"] as const;
export type Health = (typeof HEALTHS)[number];

const isHealth = (v: string): v is Health => (HEALTHS as readonly string[]).includes(v);

export const toHealth = (v: string | null | undefined): Health => (typeof v === "string" && isHealth(v) ? v : "unknown");
