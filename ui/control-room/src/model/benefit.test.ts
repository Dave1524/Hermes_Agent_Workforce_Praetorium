import { activeWorkflow } from "@/api/fixtures.test-helpers";
import { toBenefit } from "./benefit";

describe("toBenefit", () => {
  it("maps the ledger entry", () => {
    expect(toBenefit(activeWorkflow.benefit)).toEqual({
      decision: "Keep",
      eligibleRuns: 12,
      validArtifactRate: 0.92,
      latencySeconds: 150,
      consumption: { status: "measured", value: { opened: 10, approved: 4, sent: 0, markedUseful: 3, artifactRuns: 11 } },
      manualMinutesAvoided: 120,
      decidedAt: "2026-09-10T00:00:00Z",
      decidedBy: "dave",
    });
  });
  it("is null without an entry", () => {
    expect(toBenefit(null)).toBeNull();
  });
  it("keeps consumption unavailable", () => {
    expect(toBenefit({ ...activeWorkflow.benefit!, consumption: { status: "unavailable" } })?.consumption).toEqual({ status: "unavailable" });
  });
});
