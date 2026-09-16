import { fireEvent, screen, waitFor } from "@testing-library/react";
import { activeWorkflow, overview, pausedWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Workflows from "./Workflows";

const list = { apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items: [activeWorkflow, pausedWorkflow, unavailableWorkflow] };

describe("Workflows", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists every workflow as a link with health, control state and measurements", async () => {
    mockFetch({ "/api/v1/workflows": list });
    renderInShell(<Workflows />);
    await waitFor(() => expect(screen.getByTestId("workflow-count")).toHaveTextContent("3 of 3 workflows"));
    expect(screen.getByRole("link", { name: "Raw ingest" })).toHaveAttribute("href", "/app/workflows/raw-ingest");
    expect(document.querySelectorAll("[data-health='healthy']")).toHaveLength(1);
    expect(document.querySelectorAll("[data-health='unknown']")).toHaveLength(1);
    expect(document.querySelectorAll("[data-control='paused']")).toHaveLength(1);
    expect(screen.getAllByText("unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("1.5k")).toBeInTheDocument();
  });

  it("filters by health, owner, control state and text", async () => {
    mockFetch({ "/api/v1/workflows": list });
    renderInShell(<Workflows />);
    await waitFor(() => expect(screen.getByTestId("workflow-count")).toHaveTextContent("3 of 3"));
    fireEvent.change(screen.getByLabelText("Health"), { target: { value: "failed" } });
    expect(screen.getByTestId("workflow-count")).toHaveTextContent("1 of 3");
    fireEvent.change(screen.getByLabelText("Health"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "marcus" } });
    expect(screen.getByTestId("workflow-count")).toHaveTextContent("1 of 3");
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Control"), { target: { value: "unknown" } });
    expect(screen.getByTestId("workflow-count")).toHaveTextContent("1 of 3");
    fireEvent.change(screen.getByLabelText("Control"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Filter workflows"), { target: { value: "weekly" } });
    expect(screen.getByTestId("workflow-count")).toHaveTextContent("1 of 3");
    fireEvent.change(screen.getByLabelText("Filter workflows"), { target: { value: "zzz" } });
    expect(screen.getByText(/No workflows match/)).toBeInTheDocument();
  });
});
