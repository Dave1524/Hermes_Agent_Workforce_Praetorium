export const OUTCOMES = ["artifact", "decline", "failed", "skipped", "running", "unknown"] as const;
export type Outcome = (typeof OUTCOMES)[number];

const isOutcome = (v: string): v is Outcome => (OUTCOMES as readonly string[]).includes(v);

export const toOutcome = (v: string | null | undefined): Outcome => (typeof v === "string" && isOutcome(v) ? v : "unknown");
