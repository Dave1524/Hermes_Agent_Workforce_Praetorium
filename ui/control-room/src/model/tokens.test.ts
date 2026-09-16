import { formatCost, formatTokens, formatUsage } from "./tokens";

describe("tokens", () => {
  it.each([
    [0, "0"],
    [999, "999"],
    [1500, "1.5k"],
    [6000, "6.0k"],
    [1_250_000, "1.25M"],
  ])("%d -> %s", (n, s) => {
    expect(formatTokens(n)).toBe(s);
  });
  it("renders measurements", () => {
    expect(formatUsage({ status: "measured", value: { input: 1, output: 2, cache: 0, total: 1500 } })).toBe("1.5k");
    expect(formatUsage({ status: "unavailable" })).toBe("unavailable");
    expect(formatUsage({ status: "unknown" })).toBe("unknown");
    expect(formatCost({ status: "measured", value: { amount: 0.42, currency: "USD" } })).toBe("$0.42");
    expect(formatCost({ status: "measured", value: { amount: 1.5, currency: "EUR" } })).toBe("1.50 EUR");
    expect(formatCost({ status: "unavailable" })).toBe("unavailable");
  });
});
