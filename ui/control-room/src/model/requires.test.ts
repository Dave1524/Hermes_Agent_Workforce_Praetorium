import { agentOfUnit, enabledDependents, firstUnsatisfied, requiresStatus, toDependent, toRequirement } from "./requires";

const up = toRequirement({ unit: "buzz-agent@marcus", scope: "user", workflow: "buzz-agent@marcus", state: "active", satisfied: true });
const down = toRequirement({ unit: "ollama.service", scope: "system", workflow: null, state: "inactive", satisfied: false });
const unknown = toRequirement({ unit: "buzz-notion-broker", scope: "user", workflow: null, state: "unknown", satisfied: null });

describe("requires", () => {
  it("maps a requirement and names the agent behind a runtime unit", () => {
    expect(up).toEqual({ unit: "buzz-agent@marcus", scope: "user", workflow: "buzz-agent@marcus", agent: "marcus", state: "active", satisfied: true });
    expect(down.agent).toBeNull();
    expect(toRequirement({ unit: "x" })).toEqual({ unit: "x", scope: null, workflow: null, agent: null, state: "unknown", satisfied: null });
  });
  it.each([
    ["buzz-agent@augustus", "augustus"],
    ["buzz-agent@augustus.service", "augustus"],
    ["buzz-agent@", null],
    ["ollama.service", null],
  ])("agentOfUnit(%s) -> %o", (unit, agent) => {
    expect(agentOfUnit(unit)).toBe(agent);
  });
  it.each([
    [[up], "satisfied"],
    [[up, unknown], "unknown"],
    [[up, unknown, down], "down"],
    [[], "satisfied"],
  ])("status of %o is %s", (rows, status) => {
    expect(requiresStatus(rows)).toBe(status);
  });
  it("names the first unsatisfied unit and the enabled dependents", () => {
    expect(firstUnsatisfied([up, down, { ...down, unit: "later" }])?.unit).toBe("ollama.service");
    expect(firstUnsatisfied([up, unknown])).toBeNull();
    const deps = [toDependent({ workflow: "a", enabled: true }), toDependent({ workflow: "b", enabled: false }), toDependent({ workflow: "c" })];
    expect(deps[2]).toEqual({ workflow: "c", enabled: null });
    expect(enabledDependents(deps).map((d) => d.workflow)).toEqual(["a"]);
  });
});
