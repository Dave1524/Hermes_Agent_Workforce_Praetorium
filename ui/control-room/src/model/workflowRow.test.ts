import { activeWorkflow, pausedWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
import { toWorkflowRow } from "./workflowRow";

describe("toWorkflowRow", () => {
  it("maps an active workflow", () => {
    const row = toWorkflowRow(activeWorkflow);
    expect(row).toMatchObject({
      id: "agent-inbox-sync",
      name: "Agent inbox sync",
      owner: "marcus",
      health: "healthy",
      controlState: "active",
      lastRunAt: "2026-09-14T07:02:30Z",
      lastOutcome: "artifact",
      nextRunAt: "2026-09-14T07:15:00Z",
      nextRunEstimated: false,
      cadenceSeconds: 900,
      lifecycle: "active",
    });
    expect(row.usage).toEqual({ status: "measured", value: { input: 1200, output: 300, cache: 0, total: 1500 } });
  });
  it("maps a paused failed workflow with an estimated next run", () => {
    const row = toWorkflowRow(pausedWorkflow);
    expect(row).toMatchObject({ health: "failed", controlState: "paused", lastOutcome: "failed", nextRunEstimated: true });
    expect(row.usage).toEqual({ status: "unavailable" });
  });
  it("maps the all-unavailable workflow without inventing values", () => {
    const row = toWorkflowRow(unavailableWorkflow);
    expect(row).toMatchObject({ owner: null, health: "unknown", controlState: "unknown", lastRunAt: null, lastOutcome: "unknown", nextRunAt: null, cadenceSeconds: null });
    expect(row.cost).toEqual({ status: "unavailable" });
  });
});
