import { screen, waitFor } from "@testing-library/react";
import { activeWorkflow, failedRun, overview, pausedWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import WorkflowDetail from "./WorkflowDetail";

const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items });

describe("WorkflowDetail", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders header, triggers, latest output, runs and benefit from the API", async () => {
    mockFetch({ "/api/v1/workflows/raw-ingest": envelope(pausedWorkflow), "/api/v1/workflows/raw-ingest/runs": envelope([failedRun]) });
    renderInShell(<WorkflowDetail workflowId="raw-ingest" />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Raw ingest" })).toBeInTheDocument());
    expect(document.querySelector("[data-health='failed']")).toBeInTheDocument();
    expect(document.querySelector("[data-control='paused']")).toBeInTheDocument();
    expect(screen.getAllByTestId("trigger")).toHaveLength(1);
    expect(screen.getAllByText("agent-inbox-sync.timer").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("assertion failed: proposal-or-decline")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("link", { name: "run-0913" })).toHaveLength(2));
    expect(screen.getAllByRole("link", { name: "run-0913" })[0]).toHaveAttribute("href", "/app/runs/run-0913");
    expect(document.querySelector("[data-decision='Improve']")).toBeInTheDocument();
    expect(screen.getAllByText("unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("contract-sentence")).toHaveTextContent("When timer occurs, this workflow produces notion row for dave, so dave can review.");
  });

  it("shows consumption bars for a measured ledger entry", async () => {
    mockFetch({ "/api/v1/workflows/agent-inbox-sync": envelope(activeWorkflow), "/api/v1/workflows/agent-inbox-sync/runs": envelope([]) });
    renderInShell(<WorkflowDetail workflowId="agent-inbox-sync" />);
    await waitFor(() => expect(screen.getByLabelText("Opened")).toHaveAttribute("value", "10"));
    expect(screen.getByText("10 of 11")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("No runs recorded.")).toBeInTheDocument());
  });

  it("renders the all-unavailable workflow without crashing", async () => {
    mockFetch({ "/api/v1/workflows/weekly-pre-assembly": envelope(unavailableWorkflow), "/api/v1/workflows/weekly-pre-assembly/runs": envelope([]) });
    renderInShell(<WorkflowDetail workflowId="weekly-pre-assembly" />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Weekly pre-assembly" })).toBeInTheDocument());
    expect(screen.getByText("No triggers wired to this workflow.")).toBeInTheDocument();
    expect(screen.getByText("No benefit ledger entry for this workflow.")).toBeInTheDocument();
    expect(document.querySelector("[data-health='unknown']")).toBeInTheDocument();
  });

  it("shows a 404 as an error notice", async () => {
    mockFetch({ "/api/v1/workflows/nope": { status: 404, body: { error: "workflow not found" } } });
    renderInShell(<WorkflowDetail workflowId="nope" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: workflow not found"));
  });
});
