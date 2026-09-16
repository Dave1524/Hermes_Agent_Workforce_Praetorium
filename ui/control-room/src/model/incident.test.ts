import { openIncident } from "@/api/fixtures.test-helpers";
import { toIncident, toSeverity } from "./incident";

describe("incidents", () => {
  it("maps an open incident", () => {
    expect(toIncident(openIncident)).toMatchObject({ id: "inc-1", status: "open", severity: "high", workflowId: "raw-ingest", agent: "claudius", runId: "run-0913", observations: 3 });
  });
  it.each([
    ["critical", "critical"],
    ["high", "high"],
    ["medium", "medium"],
    ["low", "low"],
    ["P1", "unknown"],
    [null, "unknown"],
  ])("severity %o -> %s", (v, expected) => {
    expect(toSeverity(v)).toBe(expected);
  });
});
