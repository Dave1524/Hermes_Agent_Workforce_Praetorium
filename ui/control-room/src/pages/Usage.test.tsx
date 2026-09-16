import { screen, waitFor } from "@testing-library/react";
import { activeWorkflow, measuredUsage, overview, pausedWorkflow, unavailableUsage } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Usage from "./Usage";

const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items });

describe("Usage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("totals measured agents only and says how many were measured", async () => {
    mockFetch({ "/api/v1/usage": envelope([measuredUsage, unavailableUsage]), "/api/v1/workflows": envelope([activeWorkflow, pausedWorkflow]) });
    renderInShell(<Usage />);
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("6.0k"));
    expect(screen.getByTestId("stat-tokens")).toHaveTextContent("1 of 2 agents measured");
    expect(screen.getByTestId("stat-cost")).toHaveTextContent("1.68 USD");
    expect(screen.getAllByTestId("agent-row")).toHaveLength(2);
    expect(screen.getAllByText("unavailable").length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(screen.getByRole("link", { name: "Raw ingest" })).toBeInTheDocument());
  });

  it("says unavailable when no agent is measured", async () => {
    mockFetch({ "/api/v1/usage": envelope([unavailableUsage]), "/api/v1/workflows": envelope([]) });
    renderInShell(<Usage />);
    await waitFor(() => expect(screen.getByTestId("stat-tokens")).toHaveTextContent("unavailable"));
    expect(screen.getByTestId("stat-cost")).toHaveTextContent("unavailable");
    expect(screen.getByTestId("usage-chart")).toHaveTextContent("nothing to chart");
  });
});
