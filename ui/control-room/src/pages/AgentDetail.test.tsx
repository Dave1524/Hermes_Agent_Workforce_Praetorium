import { screen, waitFor } from "@testing-library/react";
import { agentUp, interactionTurn, overview } from "@/api/fixtures.test-helpers";
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
  });

  it("shows a 404 as an error notice", async () => {
    mockFetch({ "/api/v1/agents/nope": { status: 404, body: { error: "agent not found" } } });
    renderInShell(<AgentDetail name="nope" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: agent not found"));
  });
});
