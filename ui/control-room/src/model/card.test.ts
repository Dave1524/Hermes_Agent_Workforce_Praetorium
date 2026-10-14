import { activityText, briefProvenance, formatDay, formatResearchOn, joinResearchOn, latestQuestions, moveLabel, splitResearchOn } from "./card";

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

  it("splits and joins a research time in both forms, date-only staying a date", () => {
    expect(splitResearchOn("2026-10-14")).toEqual({ date: "2026-10-14", time: "" });
    expect(splitResearchOn("2026-10-14T06:30")).toEqual({ date: "2026-10-14", time: "06:30" });
    expect(splitResearchOn("")).toEqual({ date: "", time: "" });
    expect(joinResearchOn("2026-10-14", "")).toBe("2026-10-14");
    expect(joinResearchOn("2026-10-14", "06:30")).toBe("2026-10-14T06:30");
    expect(joinResearchOn("", "06:30")).toBe("");
    for (const value of ["2026-10-14", "2026-10-14T06:30"]) {
      const { date, time } = splitResearchOn(value);
      expect(joinResearchOn(date, time)).toBe(value);
    }
  });

  it("shows a research time as the card does", () => {
    expect(formatResearchOn("2026-10-14T06:30")).toBe("2026-10-14 06:30");
    expect(formatResearchOn("2026-10-14")).toBe("2026-10-14");
    expect(formatResearchOn(null)).toBeNull();
  });

  it("formats a scheduled day with its time when there is one", () => {
    expect(formatDay("2026-10-14T06:30")).toBe("Wed 14 Oct 06:30");
  });

  it("words the agent's questions and Dave's answer", () => {
    expect(activityText({ kind: "note", actor: "run:b3", detail: "which vendors?", noteKind: "questions" })).toBe("Questions from A run: which vendors?");
    expect(activityText({ kind: "note", actor: "dave", detail: "only EU", noteKind: "answer" })).toBe("Answer by Dave: only EU");
    expect(moveLabel("delete")).toBe("Delete");
    expect(moveLabel("restore")).toBe("Restore");
  });

  it("finds the newest questions note", () => {
    const rows = [
      { ts: "2026-10-14T09:00:00Z", kind: "note", actor: "run:b3", detail: "new", noteKind: "questions" },
      { ts: "2026-10-13T09:00:00Z", kind: "note", actor: "run:b2", detail: "old", noteKind: "questions" },
    ];
    expect(latestQuestions(rows)?.detail).toBe("new");
    expect(latestQuestions([...rows].reverse())?.detail).toBe("new");
    expect(latestQuestions([])).toBeNull();
  });
});
