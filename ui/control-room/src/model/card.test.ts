import { activityText, briefProvenance, formatDay, moveLabel } from "./card";

describe("card model", () => {
  it("formats a day as the mockup does, in UTC, from a date or a timestamp", () => {
    expect(formatDay("2026-10-06")).toBe("Tue 6 Oct");
    expect(formatDay("2026-09-28T23:30:00Z")).toBe("Mon 28 Sep");
    expect(formatDay(null)).toBeNull();
    expect(formatDay("soon")).toBeNull();
  });

  it("states brief provenance with version, author and approval day", () => {
    expect(briefProvenance({ version: 2, by: "run:b2", approved: true, approvedAt: "2026-09-28T10:00:00Z" })).toBe("v2 by A run, approved 28 Sep");
    expect(briefProvenance({ version: 1, by: "buzz:claudius", approved: false })).toBe("v1 by Claudius");
    expect(briefProvenance({ version: 3, by: "dave", approved: true })).toBe("v3 by Dave, approved");
  });

  it("words each activity row from its kind, and falls back to the kind", () => {
    expect(activityText({ kind: "brief_returned", actor: "dave", detail: "too wide" })).toBe("Brief returned by Dave: too wide");
    expect(activityText({ kind: "created", actor: "mac:claude" })).toBe("Created by Claude");
    expect(activityText({ kind: "brief", actor: "run:b1", detail: "v1" })).toBe("Brief v1 by A run");
    expect(activityText({ kind: "picked", actor: "run:r1", detail: "research", outcome: "artifact" })).toBe("Research run, artifact");
    expect(activityText({ kind: "picked", actor: "run:r1", detail: "brief" })).toBe("Brief run, running");
    expect(activityText({ kind: "edited", actor: "dave", detail: "deadline, tags" })).toBe("Edited by Dave: deadline, tags");
    expect(activityText({ kind: "mystery", actor: "dave" })).toBe("mystery");
  });

  it("labels every move the read model can state and passes an unknown one through", () => {
    expect(moveLabel("request_changes")).toBe("Request changes");
    expect(moveLabel("something_new")).toBe("something_new");
  });
});
