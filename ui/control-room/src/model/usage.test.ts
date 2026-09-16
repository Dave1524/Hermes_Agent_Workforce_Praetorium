import { measuredUsage, unavailableUsage } from "@/api/fixtures.test-helpers";
import { toAgentUsage, totalCost } from "./usage";

describe("usage", () => {
  it("maps measured and unavailable agents", () => {
    expect(toAgentUsage(measuredUsage)).toEqual({ agent: "marcus", runs: 4, usage: { status: "measured", value: { input: 4800, output: 1200, cache: 0, total: 6000 } }, cost: { status: "measured", value: { amount: 1.68, currency: "USD" } } });
    expect(toAgentUsage(unavailableUsage)).toEqual({ agent: "trajan", runs: 1, usage: { status: "unavailable" }, cost: { status: "unavailable" } });
  });
  it("totals only measured costs and says how many were not", () => {
    const rows = [measuredUsage, unavailableUsage, { ...measuredUsage, agent: "claudius" }].map(toAgentUsage);
    expect(totalCost(rows)).toEqual({ amount: 3.36, currency: "USD", measured: 2, unmeasured: 1 });
    expect(totalCost([toAgentUsage(unavailableUsage)])).toEqual({ amount: null, currency: null, measured: 0, unmeasured: 1 });
  });
});
