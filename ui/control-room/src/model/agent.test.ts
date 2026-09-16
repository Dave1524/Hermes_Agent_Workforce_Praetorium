import { agentDown, agentPaused, agentUp } from "@/api/fixtures.test-helpers";
import { toAgent, toRuntimeStatus } from "./agent";

describe("toAgent", () => {
  it("maps a live agent with a last turn, measured usage and its dependents", () => {
    const a = toAgent(agentUp);
    expect(a).toMatchObject({
      name: "marcus",
      title: "Chief of staff",
      harness: "claude-agent-acp",
      runtime: { unit: "buzz-agent@marcus", scope: "user", state: "active", status: "up", since: "2026-09-13T21:04:35Z", unitFileState: "enabled" },
      actions: [
        { id: "start", enabled: false, reason: "runtime is active, not paused" },
        { id: "stop", enabled: true, reason: null },
        { id: "restart", enabled: true, reason: null },
      ],
      health: "healthy",
      turns7d: 3,
      ownedWorkflows: [{ id: "agent-inbox-sync", role: "agent-workflow" }],
      requiredBy: [{ workflow: "agent-inbox-sync", enabled: true }],
    });
    expect(a.lastTurn?.id).toBe("turn-0914");
    expect(a.usage7d).toEqual({ status: "measured", value: { input: 4800, output: 1200, cache: 0, total: 6000 } });
    expect(a.cost7d).toEqual({ status: "measured", value: { amount: 1.68, currency: "USD" } });
  });
  it("maps an agent the bus cannot see without inventing values", () => {
    const a = toAgent(agentDown);
    expect(a.runtime).toEqual({ unit: "buzz-agent@aurelian", scope: "user", state: "unknown", status: "unknown", since: null, unitFileState: "unknown" });
    expect(a.actions.map((x) => [x.id, x.enabled, x.reason])).toEqual([
      ["start", false, "systemd state unavailable"],
      ["stop", false, "systemd state unavailable"],
      ["restart", false, "systemd state unavailable"],
    ]);
    expect(a.health).toBe("unknown");
    expect(a.lastTurn).toBeNull();
    expect(a.usage7d).toEqual({ status: "unavailable" });
    expect(a.ownedWorkflows).toEqual([]);
  });
  it("maps a fleet-off agent: start offered, the boot policy carried as a fact", () => {
    const a = toAgent(agentPaused);
    expect(a.runtime).toMatchObject({ state: "inactive", status: "down", unitFileState: "disabled" });
    expect(a.actions.map((x) => [x.id, x.enabled])).toEqual([["start", true], ["stop", false], ["restart", false]]);
  });
  it("maps a payload without control to no actions rather than inventing a vocabulary", () => {
    const a = toAgent({ ...agentPaused, control: null, runtime: { ...agentPaused.runtime, unitFileState: null } });
    expect(a.actions).toEqual([]);
    expect(a.runtime.unitFileState).toBeNull();
  });
  it.each([
    ["active", "up"],
    ["activating", "up"],
    ["reloading", "up"],
    ["inactive", "down"],
    ["failed", "down"],
    ["unknown", "unknown"],
    [null, "unknown"],
  ])("runtime state %o -> %s", (state, status) => {
    expect(toRuntimeStatus(state)).toBe(status);
  });
});
