import { activeWorkflow, pausedWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
import { toWorkflowDetail } from "./workflowDetail";

describe("toWorkflowDetail", () => {
  it("carries the row plus contract, triggers, lineage, benefit, links and actions", () => {
    const d = toWorkflowDetail(activeWorkflow);
    expect(d.row.id).toBe("agent-inbox-sync");
    expect(d.purpose).toBe("Mirror the agent inbox into Notion");
    expect(d.contract?.artifact).toBe("notion row");
    expect(d.triggers[0]).toMatchObject({ unit: "agent-inbox-sync.timer", timerState: "active", nextRunAt: "2026-09-14T07:15:00Z", spec: "*:0/15" });
    expect(d.lineage.map((s) => s.stage)).toEqual(["trigger", "runner", "artifact"]);
    expect(d.benefit?.decision).toBe("Keep");
    expect(d.links?.contractGithub).toContain("github.com");
    expect(d.actions.find((a) => a.id === "pause")).toEqual({ id: "pause", enabled: true, reason: null });
    expect(d.lastRun?.id).toBe("run-0914");
  });
  it("keeps the paused workflow's enabled resume/retry", () => {
    const d = toWorkflowDetail(pausedWorkflow);
    expect(d.actions.filter((a) => a.enabled).map((a) => a.id)).toEqual(["resume", "run_now", "retry"]);
  });
  it("renders the all-unavailable workflow as empty, not broken", () => {
    const d = toWorkflowDetail(unavailableWorkflow);
    expect(d.contract).toBeNull();
    expect(d.triggers).toEqual([]);
    expect(d.benefit).toBeNull();
    expect(d.actions).toEqual([]);
    expect(d.lastRun).toBeNull();
  });
});
