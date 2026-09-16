import { FIXTURE_NOW } from "@/api/fixtures.test-helpers";
import { durationSeconds, formatDuration, formatUtc, relativeTime } from "./time";

describe("time", () => {
  it.each([
    ["2026-09-14T07:59:40Z", "20s ago"],
    ["2026-09-14T07:02:30Z", "57m ago"],
    ["2026-09-14T03:00:00Z", "5h ago"],
    ["2026-09-11T08:00:00Z", "3d ago"],
    ["2026-09-14T08:15:00Z", "in 15m"],
    ["2026-09-16T03:00:00Z", "in 1d"],
  ])("%s -> %s", (iso, expected) => {
    expect(relativeTime(iso, FIXTURE_NOW)).toBe(expected);
  });
  it.each([null, undefined, "", "not a date"])("%o -> null", (v) => {
    expect(relativeTime(v, FIXTURE_NOW)).toBeNull();
  });
  it("formats UTC compactly", () => {
    expect(formatUtc("2026-09-14T07:02:30Z")).toBe("2026-09-14 07:02Z");
    expect(formatUtc(null)).toBeNull();
  });
  it("computes and formats durations", () => {
    expect(durationSeconds("2026-09-14T07:00:00Z", "2026-09-14T07:02:30Z")).toBe(150);
    expect(durationSeconds("2026-09-14T07:00:00Z", null)).toBeNull();
    expect(formatDuration(150)).toBe("2m 30s");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(3720)).toBe("1h 2m");
    expect(formatDuration(null)).toBeNull();
  });
});
