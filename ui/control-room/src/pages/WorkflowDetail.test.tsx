import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { activeWorkflow, failedRun, overview, pausedWorkflow, runtimeWorkflow, unavailableWorkflow } from "@/api/fixtures.test-helpers";
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
    expect(screen.getByTestId("lineage").querySelectorAll("li")).toHaveLength(6);
    expect(within(screen.getByTestId("lineage")).getAllByText("Unknown")).toHaveLength(6);
    expect(screen.getByText("No benefit ledger entry for this workflow.")).toBeInTheDocument();
    expect(document.querySelector("[data-health='unknown']")).toBeInTheDocument();
  });

  it.each([
    ["raw-ingest", pausedWorkflow, "down", "false"],
    ["agent-inbox-sync", activeWorkflow, "satisfied", "true"],
    ["weekly-pre-assembly", unavailableWorkflow, "unknown", "unknown"],
  ])("%s renders its requires chip as %s and the panel rows", async (id, workflow, status, satisfied) => {
    mockFetch({ [`/api/v1/workflows/${id}`]: envelope(workflow), [`/api/v1/workflows/${id}/runs`]: envelope([]) });
    renderInShell(<WorkflowDetail workflowId={id} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: workflow.name })).toBeInTheDocument());
    expect(screen.getByTestId("requires-chip")).toHaveAttribute("data-requires", status);
    expect(screen.getAllByTestId("requirement")[0]).toHaveAttribute("data-satisfied", satisfied);
    expect(screen.getByText("Nothing requires this workflow.")).toBeInTheDocument();
  });

  it("shows the guards chip and lists dependents on a runtime row", async () => {
    mockFetch({ "/api/v1/workflows/buzz-agent%40marcus": envelope(runtimeWorkflow), "/api/v1/workflows/buzz-agent%40marcus/runs": envelope([]) });
    renderInShell(<WorkflowDetail workflowId="buzz-agent@marcus" />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "buzz-agent@marcus" })).toBeInTheDocument());
    expect(screen.queryByTestId("requires-chip")).toBeNull();
    expect(screen.getByTestId("dependent")).toHaveAttribute("data-enabled", "true");
    expect(within(screen.getByTestId("dependent")).getByRole("link", { name: "agent-inbox-sync" })).toHaveAttribute("href", "/app/workflows/agent-inbox-sync");
    mockFetch({ "/api/v1/workflows/weekly-pre-assembly": envelope(unavailableWorkflow), "/api/v1/workflows/weekly-pre-assembly/runs": envelope([]) });
    renderInShell(<WorkflowDetail workflowId="weekly-pre-assembly" />);
    await waitFor(() => expect(screen.getByTestId("guards-chip")).toHaveAttribute("title", "Without it the weekly pre-read is never assembled."));
  });

  it("renders a contract exemption as a declaration, not an error", async () => {
    const spent = { ...unavailableWorkflow, id: "nekovri-subsidy-kickoff", name: "NeKoVri kickoff", lifecycle: "spent", contractStatus: "exempt", contractError: null, contractExempt: "spent: its one date fired 2026-08-03" };
    mockFetch({ "/api/v1/workflows/nekovri-subsidy-kickoff": envelope(spent), "/api/v1/workflows/nekovri-subsidy-kickoff/runs": envelope([]) });
    renderInShell(<WorkflowDetail workflowId="nekovri-subsidy-kickoff" />);
    await waitFor(() => expect(screen.getByTestId("contract-status")).toHaveTextContent("exempt · spent: its one date fired 2026-08-03"));
    expect(screen.getByTestId("contract-status").querySelector(".text-red")).toBeNull();
  });

  it("shows a 404 as an error notice", async () => {
    mockFetch({ "/api/v1/workflows/nope": { status: 404, body: { error: "workflow not found" } } });
    renderInShell(<WorkflowDetail workflowId="nope" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: workflow not found"));
  });
});

describe("WorkflowDetail controls", () => {
  afterEach(() => vi.unstubAllGlobals());

  const proposalsList = { stage: "list", items: [{ proposal_id: "p-7", kind: "schedule", stage: "submitted", reason: "earlier", completed_at: "2026-09-13T10:00:00Z", pr: { url: "https://github.com/x/y/pull/7", number: 7 } }] };

  it("renders one button per action from the API, disabled ones carrying the reason", async () => {
    mockFetch({ "/api/v1/workflows/raw-ingest": envelope(pausedWorkflow), "/api/v1/workflows/raw-ingest/runs": envelope([failedRun]), "/api/v1/control/proposals": proposalsList });
    renderInShell(<WorkflowDetail workflowId="raw-ingest" />);
    const controls = await screen.findByTestId("controls");
    expect(within(controls).getByRole("button", { name: "Pause" })).toBeDisabled();
    expect(within(controls).getByRole("button", { name: "Pause" })).toHaveAttribute("title", "already paused");
    expect(within(controls).getByRole("button", { name: "Resume" })).toBeEnabled();
    expect(within(controls).getByRole("button", { name: "Run now" })).toBeEnabled();
    expect(within(controls).getByRole("button", { name: "Retry" })).toBeEnabled();
    expect(within(controls).getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(within(controls).queryByRole("button", { name: /ack|approve|reject/i })).toBeNull();
  });

  it("renders no buttons when the API offers no actions", async () => {
    mockFetch({ "/api/v1/workflows/weekly-pre-assembly": envelope(unavailableWorkflow), "/api/v1/workflows/weekly-pre-assembly/runs": envelope([]), "/api/v1/control/proposals": { stage: "list", items: [] } });
    renderInShell(<WorkflowDetail workflowId="weekly-pre-assembly" />);
    const controls = await screen.findByTestId("controls");
    expect(within(controls).queryAllByRole("button", { name: /pause|resume|run now|retry|stop/i })).toHaveLength(0);
    expect(within(controls).getByText(/no control actions/i)).toBeInTheDocument();
  });

  it("lists existing proposals and offers Change schedule and Retire", async () => {
    const { calls } = mockFetch({ "/api/v1/workflows/raw-ingest": envelope(pausedWorkflow), "/api/v1/workflows/raw-ingest/runs": envelope([failedRun]), "/api/v1/control/proposals": proposalsList });
    renderInShell(<WorkflowDetail workflowId="raw-ingest" />);
    await screen.findByRole("link", { name: /#7/ });
    expect(screen.getByRole("link", { name: /#7/ })).toHaveAttribute("href", "https://github.com/x/y/pull/7");
    const listCall = calls.find((c) => c.path === "/api/v1/control/proposals");
    expect(JSON.parse(String(listCall!.init?.body))).toEqual({ workflow_id: "raw-ingest", kind: "schedule", stage: "list" });
    fireEvent.click(screen.getByRole("button", { name: /more/i }));
    expect(screen.getByRole("menuitem", { name: /change schedule/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /retire/i })).toBeInTheDocument();
  });

  it("an applied action re-fetches the workflow, redraws the control state and shows the receipt", async () => {
    const previewed = { receipt: { receipt_id: "rcpt-8", result: "previewed", action: "resume", stage: "preview" }, control: pausedWorkflow.control, preview: { preview_token: "rcpt-8", implication: { catchUp: false } } };
    const applied = { receipt: { receipt_id: "rcpt-9", result: "applied", action: "resume", stage: "apply", before: { state: "paused" }, after: { state: "active" }, next_scheduled_run: "2026-09-16T03:00:00Z" }, control: { ...pausedWorkflow.control, state: "active" } };
    const resumed = { ...pausedWorkflow, control: { ...pausedWorkflow.control, state: "active", lastAction: applied.receipt } };
    const { calls } = mockFetch({
      "/api/v1/workflows/raw-ingest": [envelope(pausedWorkflow), envelope(resumed)],
      "/api/v1/workflows/raw-ingest/runs": envelope([failedRun]),
      "/api/v1/control/proposals": { stage: "list", items: [] },
      "/api/v1/control/actions": [previewed, applied],
    });
    renderInShell(<WorkflowDetail workflowId="raw-ingest" />);
    const controls = await screen.findByTestId("controls");
    expect(within(controls).getByText(/no control action recorded/i)).toBeInTheDocument();
    fireEvent.click(within(controls).getByRole("button", { name: "Resume" }));
    const dialog = await screen.findByRole("dialog", { name: /resume/i });
    fireEvent.click(within(dialog).getByRole("button", { name: "Preview" }));
    await within(dialog).findByTestId("implication");
    fireEvent.click(within(dialog).getByRole("button", { name: /apply with this preview/i }));
    await waitFor(() => expect(document.querySelector("[data-control='active']")).toBeInTheDocument());
    expect(calls.filter((c) => c.path === "/api/v1/workflows/raw-ingest")).toHaveLength(2);
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    const receipt = within(controls).getByTestId("receipt");
    expect(receipt).toHaveAttribute("data-result", "applied");
    expect(receipt).toHaveTextContent("rcpt-9");
    expect(receipt).toHaveTextContent(/paused → active/);
  });
});
