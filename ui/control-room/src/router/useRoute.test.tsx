import { act, renderHook } from "@testing-library/react";
import { matchRoute, routeHref } from "./routes";
import { navigate, useRoute } from "./useRoute";

describe("matchRoute", () => {
  it.each([
    ["/app", { name: "overview" }],
    ["/app/", { name: "overview" }],
    ["/app/workflows", { name: "workflows" }],
    ["/app/workflows/", { name: "workflows" }],
    ["/app/workflows/raw-ingest", { name: "workflow", id: "raw-ingest" }],
    ["/app/runs/run-0913", { name: "run", id: "run-0913" }],
    ["/app/incidents", { name: "incidents" }],
    ["/app/usage", { name: "usage" }],
    ["/app/activity", { name: "activity" }],
    ["/app/agents", { name: "agents" }],
    ["/app/agents/marcus", { name: "agent", id: "marcus" }],
  ])("%s", (path, expected) => {
    expect(matchRoute(path)).toEqual({ ...expected, unknown: false });
  });

  it.each(["/app/not-a-route", "/app/workflows/a/b", "/app/runs", "/elsewhere"])(
    "%s falls back to Overview flagged unknown",
    (path) => {
      expect(matchRoute(path)).toEqual({ name: "overview", unknown: true });
    },
  );

  it("decodes percent-encoded ids", () => {
    expect(matchRoute("/app/workflows/a%20b")).toEqual({ name: "workflow", id: "a b", unknown: false });
  });
});

describe("routeHref", () => {
  it.each([
    [{ name: "overview" as const }, "/app/"],
    [{ name: "workflows" as const }, "/app/workflows"],
    [{ name: "workflow" as const, id: "raw-ingest" }, "/app/workflows/raw-ingest"],
    [{ name: "run" as const, id: "run-0913" }, "/app/runs/run-0913"],
    [{ name: "incidents" as const }, "/app/incidents"],
    [{ name: "usage" as const }, "/app/usage"],
    [{ name: "activity" as const }, "/app/activity"],
    [{ name: "agents" as const }, "/app/agents"],
    [{ name: "agent" as const, id: "marcus" }, "/app/agents/marcus"],
  ])("%o -> %s", (route, href) => {
    expect(routeHref(route)).toBe(href);
  });
});

describe("useRoute", () => {
  it("reads the current location, follows navigate() and popstate", () => {
    window.history.replaceState(null, "", "/app/usage");
    const { result } = renderHook(() => useRoute());
    expect(result.current.name).toBe("usage");
    act(() => navigate({ name: "workflow", id: "raw-ingest" }));
    expect(window.location.pathname).toBe("/app/workflows/raw-ingest");
    expect(result.current).toEqual({ name: "workflow", id: "raw-ingest", unknown: false });
    act(() => {
      window.history.pushState(null, "", "/app/incidents");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(result.current.name).toBe("incidents");
  });
});
