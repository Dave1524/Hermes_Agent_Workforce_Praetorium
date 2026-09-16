import { screen, waitFor } from "@testing-library/react";
import { overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import App from "./App";
import { renderInShell } from "./render.test-helpers";

const health = { status: "ok", apiVersion: "1", generatedAt: overview.generatedAt, sources: { manifests: "available", receipts: "available" }, errors: {} };
const exceptions = { apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items: [], dataQuality: [] };

describe("App shell", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the nav as real links, the health footer and generatedAt", async () => {
    window.history.replaceState(null, "", "/app/");
    mockFetch({ "/api/v1/health": health, "/api/v1/overview": overview, "/api/v1/exceptions": exceptions });
    renderInShell(<App />);
    expect(screen.getByRole("link", { name: "Workflows" })).toHaveAttribute("href", "/app/workflows");
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(screen.getByTestId("health-status")).toHaveTextContent("ok"));
    await waitFor(() => expect(screen.getByTestId("generated-at")).toHaveTextContent(/Generated/));
  });

  it("reports degraded from a 503 with a body and unreachable otherwise", async () => {
    window.history.replaceState(null, "", "/app/");
    mockFetch({ "/api/v1/health": { status: 503, body: { ...health, status: "degraded" } }, "/api/v1/overview": overview, "/api/v1/exceptions": exceptions });
    const first = renderInShell(<App />);
    await waitFor(() => expect(screen.getByTestId("health-status")).toHaveTextContent("degraded"));
    first.unmount();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network down"); }));
    renderInShell(<App />);
    await waitFor(() => expect(screen.getByTestId("health-status")).toHaveTextContent("unreachable"));
  });

  it("lands an unknown path on Overview with a notice", async () => {
    window.history.replaceState(null, "", "/app/not-a-route");
    mockFetch({ "/api/v1/health": health, "/api/v1/overview": overview, "/api/v1/exceptions": exceptions });
    renderInShell(<App />);
    expect(screen.getByTestId("unknown-route")).toHaveTextContent("/app/not-a-route is not a Control Room view");
    await waitFor(() => expect(screen.getByTestId("stat-workflows")).toBeInTheDocument());
  });

  it("persists the auto-refresh toggle", async () => {
    window.history.replaceState(null, "", "/app/");
    window.localStorage.removeItem("control-room.auto-refresh");
    mockFetch({ "/api/v1/health": health, "/api/v1/overview": overview, "/api/v1/exceptions": exceptions });
    renderInShell(<App />);
    const box = screen.getByRole("checkbox", { name: /auto-refresh/i });
    expect(box).toBeChecked();
    box.click();
    await waitFor(() => expect(window.localStorage.getItem("control-room.auto-refresh")).toBe("off"));
  });
});
