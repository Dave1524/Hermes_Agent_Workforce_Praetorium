import { screen, waitFor } from "@testing-library/react";
import { failedRun, measuredRun, overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import RunDetail from "./RunDetail";

const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items });

describe("RunDetail", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders a measured artifact run", async () => {
    mockFetch({ "/api/v1/runs/run-0914": envelope(measuredRun) });
    renderInShell(<RunDetail runId="run-0914" />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "run-0914" })).toBeInTheDocument());
    expect(document.querySelector("[data-outcome='artifact']")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /agent-inbox-sync/ })).toHaveAttribute("href", "/app/workflows/agent-inbox-sync");
    expect(screen.getByText("1.5k")).toBeInTheDocument();
    expect(screen.getByText("$0.42")).toBeInTheDocument();
    expect(screen.getByText("2m 30s")).toBeInTheDocument();
    expect(screen.getByTestId("assertions")).toHaveTextContent(/pass\s*row-written/);
  });

  it("renders a failed run with unavailable usage and the failed assertion", async () => {
    mockFetch({ "/api/v1/runs/run-0913": envelope(failedRun) });
    renderInShell(<RunDetail runId="run-0913" />);
    await waitFor(() => expect(document.querySelector("[data-outcome='failed']")).toBeInTheDocument());
    expect(screen.getAllByText("unavailable")).toHaveLength(2);
    expect(screen.getByTestId("assertions")).toHaveTextContent(/fail\s*proposal-or-decline\s*— neither a proposal nor DECLINE:/);
  });

  it("shows a 404 as an error notice", async () => {
    mockFetch({ "/api/v1/runs/nope": { status: 404, body: { error: "run not found" } } });
    renderInShell(<RunDetail runId="nope" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: run not found"));
  });
});
