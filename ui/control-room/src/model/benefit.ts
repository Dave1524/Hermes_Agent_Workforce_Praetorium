import type { Benefit as ApiBenefit, Consumption as ApiConsumption } from "@/api/schemas/benefit";
import type { Measurement } from "./measurement";

export const BENEFIT_DECISIONS = ["Keep", "Improve", "Retire", "Unknown"] as const;
export type BenefitDecision = (typeof BENEFIT_DECISIONS)[number];

const isDecision = (v: string): v is BenefitDecision => (BENEFIT_DECISIONS as readonly string[]).includes(v);

export const toBenefitDecision = (v: string | null | undefined): BenefitDecision =>
  typeof v === "string" && isDecision(v) ? v : "Unknown";

export interface Consumption {
  opened: number;
  approved: number;
  sent: number;
  markedUseful: number;
  artifactRuns: number;
}

export interface Benefit {
  decision: BenefitDecision;
  eligibleRuns: number | null;
  validArtifactRate: number | null;
  latencySeconds: number | null;
  consumption: Measurement<Consumption>;
  manualMinutesAvoided: number | null;
  decidedAt: string | null;
  decidedBy: string | null;
}

const toConsumption = (c: ApiConsumption | null | undefined): Measurement<Consumption> => {
  if (!c) return { status: "unknown" };
  if (c.status === "unavailable") return { status: "unavailable" };
  if (c.status !== "measured") return { status: "unknown" };
  return {
    status: "measured",
    value: { opened: c.opened ?? 0, approved: c.approved ?? 0, sent: c.sent ?? 0, markedUseful: c.marked_useful ?? 0, artifactRuns: c.artifactRuns ?? 0 },
  };
};

export const toBenefit = (b: ApiBenefit | null | undefined): Benefit | null =>
  b
    ? {
        decision: toBenefitDecision(b.decision),
        eligibleRuns: b.eligibleRuns ?? null,
        validArtifactRate: b.validArtifactRate ?? null,
        latencySeconds: b.latencySeconds ?? null,
        consumption: toConsumption(b.consumption),
        manualMinutesAvoided: b.manualMinutesAvoided ?? null,
        decidedAt: b.decidedAt ?? null,
        decidedBy: b.decidedBy ?? null,
      }
    : null;
