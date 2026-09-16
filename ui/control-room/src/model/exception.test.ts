import { failedException } from "@/api/fixtures.test-helpers";
import { EXCEPTION_KINDS, exceptionKindLabel, sortExceptions, toException } from "./exception";

describe("exceptions", () => {
  it("maps a failed row", () => {
    expect(toException(failedException)).toMatchObject({
      kind: "failed",
      workflowId: "raw-ingest",
      owner: "claudius",
      issue: "assertion failed: proposal-or-decline",
      requiredAction: "Retry after fixing the profile",
      runId: "run-0913",
      paused: true,
      since: "2026-09-13T03:04:00Z",
    });
  });
  it("keeps the API's kind order", () => {
    expect(EXCEPTION_KINDS).toEqual(["failed", "stale-input", "missing-artifact", "missed-cadence", "overdue-next-action", "unconsumed-output", "dependency-down"]);
    const rows = [{ ...failedException, kind: "unconsumed-output" }, { ...failedException, kind: "made-up" }, failedException].map(toException);
    expect(sortExceptions(rows).map((r) => r.kind)).toEqual(["failed", "unconsumed-output", "made-up"]);
  });
  it.each([
    ["failed", "Failed"],
    ["stale-input", "Stale input"],
    ["overdue-next-action", "Overdue next action"],
    ["dependency-down", "Dependency down"],
    ["made-up", "made-up"],
  ])("label %s -> %s", (kind, label) => {
    expect(exceptionKindLabel(kind)).toBe(label);
  });
});
