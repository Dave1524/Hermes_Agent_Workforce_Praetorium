import { agentDown, agentUp } from "@/api/fixtures.test-helpers";
import { toAgent, toRuntimeStatus } from "./agent";

describe("toAgent", () => {
  it("maps a live agent with a last turn, measured usage and its dependents", () => {
    const a = toAgent(agentUp);
    expect(a).toMatchObject({
      name: "marcus",
      title: "Chief of staff",
      harness: "claude-agent-acp",
      runtime: { unit: "buzz-agent@marcus", scope: "user", state: "active", status: "up", since: "2026-09-13T21:04:35Z" },
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
    expect(a.runtime).toEqual({ unit: "buzz-agent@aurelian", scope: "user", state: "unknown", status: "unknown", since: null });
    expect(a.health).toBe("unknown");
    expect(a.lastTurn).toBeNull();
    expect(a.usage7d).toEqual({ status: "unavailable" });
    expect(a.ownedWorkflows).toEqual([]);
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
