import { toBenefitDecision } from "./benefit";
import { toControlState } from "./controlState";
import { toHealth } from "./health";
import { toOutcome } from "./outcome";

describe("vocabularies fall back to unknown", () => {
  it.each(["healthy", "running", "incomplete", "failed", "paused", "unknown"] as const)("health %s", (v) => {
    expect(toHealth(v)).toBe(v);
  });
  it.each(["attention", "", null, undefined, "HEALTHY"])("health %o -> unknown", (v) => {
    expect(toHealth(v)).toBe("unknown");
  });
  it.each(["artifact", "decline", "failed", "skipped", "running"] as const)("outcome %s", (v) => {
    expect(toOutcome(v)).toBe(v);
  });
  it.each(["ok", null, undefined])("outcome %o -> unknown", (v) => {
    expect(toOutcome(v)).toBe("unknown");
  });
  it.each(["paused", "active", "running", "unknown"] as const)("control %s", (v) => {
    expect(toControlState(v)).toBe(v);
  });
  it.each(["stopped", null])("control %o -> unknown", (v) => {
    expect(toControlState(v)).toBe("unknown");
  });
  it.each(["Keep", "Improve", "Retire", "Unknown"] as const)("benefit %s", (v) => {
    expect(toBenefitDecision(v)).toBe(v);
  });
  it.each(["keep", null, undefined])("benefit %o -> Unknown", (v) => {
    expect(toBenefitDecision(v)).toBe("Unknown");
  });
});
