import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { activeWorkflow, overview, pausedWorkflow, runtimeWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Workflows from "./Workflows";

const list = { apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items: [activeWorkflow, pausedWorkflow, unavailableWorkflow, runtimeWorkflow] };

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

  it("splits agent and system workflows into two sections and never lists a runtime", async () => {
    mockFetch({ "/api/v1/workflows": list });
    renderInShell(<Workflows />);
    await waitFor(() => expect(screen.getByTestId("workflow-count")).toHaveTextContent("3 of 3 workflows"));
    const agents = screen.getByTestId("section-agent-workflow");
    const system = screen.getByTestId("section-system-workflow");
    expect(within(agents).getByRole("heading", { name: "Agent workflows" })).toBeInTheDocument();
    expect(within(agents).getByTestId("section-count")).toHaveTextContent("2 of 2");
    expect(within(system).getByRole("heading", { name: "System workflows" })).toBeInTheDocument();
    expect(within(system).getByTestId("section-count")).toHaveTextContent("1 of 1");
    expect(within(agents).getAllByRole("row")).toHaveLength(3);
    expect(within(system).getAllByRole("row")).toHaveLength(2);
    expect(within(agents).getByRole("columnheader", { name: "Tokens" })).toBeInTheDocument();
    expect(within(system).queryByRole("columnheader", { name: "Tokens" })).toBeNull();
    expect(within(system).queryByRole("columnheader", { name: "Cost" })).toBeNull();
    expect(screen.queryByText("buzz-agent@marcus")).toBeNull();
    expect(document.querySelectorAll("[data-role]")).toHaveLength(3);
  });

  it("shows a requires chip per row that declares one and a guards chip per guarded row", async () => {
    mockFetch({ "/api/v1/workflows": list });
    renderInShell(<Workflows />);
    await waitFor(() => expect(screen.getAllByTestId("requires-chip")).toHaveLength(3));
    const chipOf = (id: string) => within(document.querySelector(`[data-workflow-id='${id}']`) as HTMLElement);
    expect(chipOf("agent-inbox-sync").getByTestId("requires-chip")).toHaveAttribute("data-requires", "satisfied");
    expect(chipOf("raw-ingest").getByTestId("requires-chip")).toHaveTextContent("requires down: ollama.service");
    expect(chipOf("weekly-pre-assembly").getByTestId("requires-chip")).toHaveAttribute("data-requires", "unknown");
    expect(screen.getAllByTestId("guards-chip")).toHaveLength(1);
    expect(chipOf("weekly-pre-assembly").getByTestId("guards-chip")).toHaveAttribute("title", "Without it the weekly pre-read is never assembled.");
  });

  it("filters by health, owner, control state and text across both sections", async () => {
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
    expect(within(screen.getByTestId("section-agent-workflow")).getByTestId("section-count")).toHaveTextContent("0 of 2");
    expect(within(screen.getByTestId("section-system-workflow")).getByTestId("section-count")).toHaveTextContent("1 of 1");
    fireEvent.change(screen.getByLabelText("Control"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Filter workflows"), { target: { value: "weekly" } });
    expect(screen.getByTestId("workflow-count")).toHaveTextContent("1 of 3");
    fireEvent.change(screen.getByLabelText("Filter workflows"), { target: { value: "zzz" } });
    expect(screen.getAllByText(/No workflows match/)).toHaveLength(2);
  });
});
