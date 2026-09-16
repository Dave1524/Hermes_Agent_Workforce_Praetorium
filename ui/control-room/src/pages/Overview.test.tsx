import { screen, waitFor } from "@testing-library/react";
import { dependencyDownException, failedException, overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Overview from "./Overview";

const exceptions = { apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items: [dependencyDownException, failedException], dataQuality: [] };

describe("Overview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders summary counts, the exceptions queue, agent usage and recent outputs from the API", async () => {
    mockFetch({ "/api/v1/overview": overview, "/api/v1/exceptions": exceptions });
    renderInShell(<Overview />);
    await waitFor(() => expect(screen.getByTestId("stat-workflows")).toHaveTextContent("31"));
    expect(screen.getByTestId("stat-healthy")).toHaveTextContent("22");
    expect(screen.getByTestId("stat-paused")).toHaveTextContent("30");
    expect(screen.getByTestId("stat-agents")).toHaveTextContent("5 · 4 up");
    expect(screen.getByRole("link", { name: "marcus" })).toHaveAttribute("href", "/app/agents/marcus");
    expect(screen.getByText("assertion failed: proposal-or-decline")).toBeInTheDocument();
    const kinds = screen.getAllByTestId("exception-kind").map((el) => el.textContent);
    expect(kinds).toEqual(["Failed", "Dependency down"]);
    expect(screen.getByText("requires ollama.service (system): inactive")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "raw-ingest" })[0]).toHaveAttribute("href", "/app/workflows/raw-ingest");
    expect(screen.getByText("6.0k")).toBeInTheDocument();
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Inbox sync 2026-09-14")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "run-0914" })).toHaveAttribute("href", "/app/runs/run-0914");
  });

  it("shows the reliability panel as unavailable when receipts are, and the agents tile as — without a summary", async () => {
    mockFetch({ "/api/v1/overview": { ...overview, reliability7d: { status: "unavailable", days: [] }, summary: { ...overview.summary, agents: null } }, "/api/v1/exceptions": { ...exceptions, items: [] } });
    renderInShell(<Overview />);
    await waitFor(() => expect(screen.getByTestId("reliability")).toHaveTextContent("unavailable"));
    expect(screen.getByTestId("stat-agents")).toHaveTextContent("—");
    expect(screen.getByText(/nothing in the queue/i)).toBeInTheDocument();
  });

  it("shows an error notice when the API fails", async () => {
    mockFetch({ "/api/v1/overview": { status: 500, body: { error: "boom" } }, "/api/v1/exceptions": exceptions });
    renderInShell(<Overview />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("500: boom"));
  });
});
