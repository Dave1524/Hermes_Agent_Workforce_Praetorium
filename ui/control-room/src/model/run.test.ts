import { failedRun, measuredRun, skippedRun } from "@/api/fixtures.test-helpers";
import { toRun } from "./run";

describe("toRun", () => {
  it("maps a measured artifact run", () => {
    const r = toRun(measuredRun);
    expect(r).toMatchObject({ id: "run-0914", workflowId: "agent-inbox-sync", agent: "marcus", outcome: "artifact", durationSeconds: 150 });
    expect(r.artifact).toEqual({ uri: "notion://inbox/2026-09-14", title: "Inbox sync 2026-09-14", kind: "notion" });
    expect(r.assertions).toEqual([{ id: "row-written", status: "pass", message: null }]);
    expect(r.usage.status).toBe("measured");
  });
  it("maps a failed run with unavailable usage", () => {
    const r = toRun(failedRun);
    expect(r.outcome).toBe("failed");
    expect(r.assertions[0]).toEqual({ id: "proposal-or-decline", status: "fail", message: "neither a proposal nor DECLINE:" });
    expect(r.usage).toEqual({ status: "unavailable" });
    expect(r.nextAction).toBeNull();
  });
  it("carries an operator closure and null when there is none", () => {
    const closed = { at: "2026-09-17T10:30:00Z", by: "Dave", reason: "check defect fixed in 73dea03" };
    expect(toRun({ ...failedRun, closed }).closed).toEqual(closed);
    expect(toRun(failedRun).closed).toBeNull();
  });
  it("tolerates a run with no id and no times", () => {
    const r = toRun({ ...skippedRun, id: null, startedAt: null, endedAt: null });
    expect(r.id).toBe("");
    expect(r.durationSeconds).toBeNull();
    expect(r.outcome).toBe("skipped");
  });
});
