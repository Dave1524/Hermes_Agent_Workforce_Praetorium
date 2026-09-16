import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { agentPaused, agentUp, interactionTurn, overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import AgentDetail from "./AgentDetail";

const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items });

describe("AgentDetail", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the agent card and the recent turns from the runtime's runs", async () => {
    mockFetch({ "/api/v1/agents/marcus": envelope(agentUp), "/api/v1/workflows/buzz-agent%40marcus/runs": envelope([interactionTurn]) });
    renderInShell(<AgentDetail name="marcus" />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "marcus" })).toBeInTheDocument());
    expect(screen.getByTestId("runtime-chip")).toHaveAttribute("data-runtime", "up");
    expect(screen.getByText("design/agents/marcus.toml")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: "turn-0914" })).toHaveAttribute("href", "/app/runs/turn-0914"));
    expect(screen.getByRole("link", { name: "buzz-agent@marcus" })).toHaveAttribute("href", "/app/workflows/buzz-agent%40marcus");
    expect(screen.getByRole("button", { name: "Stop agent now" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Start agent now" })).toBeDisabled();
    expect(screen.getByText("enabled")).toBeInTheDocument();
  });

  it("Start agent now on a fleet-off agent posts confirm: true and re-fetches the agent", async () => {
    const started = { ...agentPaused, runtime: { ...agentPaused.runtime, state: "active", unitFileState: "disabled" }, control: { ...agentPaused.control, state: "active", actions: [{ id: "start", enabled: false, reason: "runtime is active, not paused" }, { id: "stop", enabled: true, reason: null }, { id: "restart", enabled: true, reason: null }] } };
    const { calls } = mockFetch({
      "/api/v1/agents/trajan": [envelope(agentPaused), envelope(started)],
      "/api/v1/workflows/buzz-agent%40trajan/runs": envelope([]),
      "/api/v1/control/actions": { receipt: { receipt_id: "rcpt-1", result: "applied", action: "start", workflow_id: "buzz-agent@trajan", after: { state: "active" } }, control: started.control },
    });
    renderInShell(<AgentDetail name="trajan" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Start agent now" })).toBeEnabled());
    expect(screen.getByTestId("runtime-chip")).toHaveAttribute("data-runtime", "down");
    fireEvent.click(screen.getByRole("button", { name: "Start agent now" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start agent now" }));
    await waitFor(() => expect(screen.getByTestId("runtime-chip")).toHaveAttribute("data-runtime", "up"));
    const post = calls.find((c) => c.path === "/api/v1/control/actions");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ workflow_id: "buzz-agent@trajan", action: "start", confirm: true });
    expect(calls.filter((c) => c.path === "/api/v1/agents/trajan")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Stop agent now" })).toBeEnabled();
  });

  it("shows a 404 as an error notice", async () => {
    mockFetch({ "/api/v1/agents/nope": { status: 404, body: { error: "agent not found" } } });
    renderInShell(<AgentDetail name="nope" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: agent not found"));
  });
});
