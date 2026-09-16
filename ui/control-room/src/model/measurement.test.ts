import { failedRun, measuredRun, measuredUsage, unavailableUsage } from "@/api/fixtures.test-helpers";
import { costFromCamel, costFromSnake, usageFromCamel, usageFromSnake } from "./measurement";

describe("measurement mappers", () => {
  it("maps a measured snake_case usage", () => {
    expect(usageFromSnake(measuredRun.usage)).toEqual({ status: "measured", value: { input: 1200, output: 300, cache: 0, total: 1500 } });
  });
  it("maps a measured camelCase usage", () => {
    expect(usageFromCamel(measuredUsage.usage)).toEqual({ status: "measured", value: { input: 4800, output: 1200, cache: 0, total: 6000 } });
  });
  it("keeps unavailable as a value, never 0", () => {
    expect(usageFromSnake(failedRun.usage)).toEqual({ status: "unavailable" });
    expect(usageFromCamel(unavailableUsage.usage)).toEqual({ status: "unavailable" });
    expect(costFromSnake(failedRun.cost)).toEqual({ status: "unavailable" });
    expect(costFromCamel(unavailableUsage.cost)).toEqual({ status: "unavailable" });
  });
  it("maps a measured cost with currency", () => {
    expect(costFromSnake(measuredRun.cost)).toEqual({ status: "measured", value: { amount: 0.42, currency: "USD" } });
    expect(costFromCamel(measuredUsage.cost)).toEqual({ status: "measured", value: { amount: 1.68, currency: "USD" } });
  });
  it.each([null, undefined, { status: "weird", total_tokens: 4 }, { status: "measured", total_tokens: null }])(
    "%o -> unknown",
    (input) => {
      expect(usageFromSnake(input)).toEqual({ status: "unknown" });
    },
  );
});
