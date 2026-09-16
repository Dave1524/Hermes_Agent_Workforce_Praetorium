import { screen, waitFor, within } from "@testing-library/react";
import { agentDown, agentUp, overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Agents from "./Agents";

const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items });

describe("Agents", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders a card per agent with runtime state, last turn, usage, owned workflows and dependents", async () => {
    mockFetch({ "/api/v1/agents": envelope([agentUp, agentDown]) });
    renderInShell(<Agents />);
    await waitFor(() => expect(screen.getByTestId("agent-count")).toHaveTextContent("2 agents · 1 up"));
    const cards = screen.getAllByTestId("agent-card");
    expect(cards).toHaveLength(2);
    const marcus = within(cards[0]!);
    expect(marcus.getByRole("link", { name: "marcus" })).toHaveAttribute("href", "/app/agents/marcus");
    expect(marcus.getByTestId("runtime-chip")).toHaveAttribute("data-runtime", "up");
    expect(marcus.getByTestId("runtime-chip")).toHaveTextContent("active");
    expect(marcus.getByTestId("last-turn")).toHaveTextContent(/ago/);
    expect(marcus.getByTestId("turns-7d")).toHaveTextContent("3");
    expect(marcus.getByText("6.0k")).toBeInTheDocument();
    expect(marcus.getAllByRole("link", { name: "agent-inbox-sync" })).toHaveLength(2);
    expect(marcus.getByText(/agent workflows:/i)).toBeInTheDocument();
    expect(within(marcus.getByTestId("required-by")).getByRole("link", { name: "agent-inbox-sync" })).toHaveAttribute("href", "/app/workflows/agent-inbox-sync");
    const aurelian = within(cards[1]!);
    expect(aurelian.getByTestId("runtime-chip")).toHaveAttribute("data-runtime", "unknown");
    expect(aurelian.getByTestId("last-turn")).toHaveTextContent("—");
    expect(aurelian.getAllByText("unavailable").length).toBeGreaterThanOrEqual(2);
    expect(aurelian.getByText(/owns no workflow/i)).toBeInTheDocument();
    expect(aurelian.queryByTestId("required-by")).toBeNull();
    expect(screen.queryByRole("button", { name: /start|stop|restart/i })).toBeNull();
  });

  it("shows an error notice when the API fails", async () => {
    mockFetch({ "/api/v1/agents": { status: 500, body: { error: "boom" } } });
    renderInShell(<Agents />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("500: boom"));
  });
});
