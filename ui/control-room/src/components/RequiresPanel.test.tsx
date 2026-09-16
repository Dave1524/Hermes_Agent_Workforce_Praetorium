import { render, screen, within } from "@testing-library/react";
import { toDependent, toRequirement } from "@/model/requires";
import RequiresPanel from "./RequiresPanel";

const runtime = toRequirement({ unit: "buzz-agent@marcus", scope: "user", workflow: "buzz-agent@marcus", state: "active", satisfied: true });
const service = toRequirement({ unit: "ollama.service", scope: "system", workflow: null, state: "inactive", satisfied: false });
const unknown = toRequirement({ unit: "qmd-mcp", scope: "system", workflow: null, state: "unknown", satisfied: null });
const other = toRequirement({ unit: "qmd-refresh", scope: "system", workflow: "qmd-refresh", state: "active", satisfied: true });

describe("RequiresPanel", () => {
  it("lists each requirement with its state and links runtimes to agents and workflows to workflows", () => {
    render(<RequiresPanel requires={[runtime, service, unknown, other]} requiredBy={[]} />);
    const rows = screen.getAllByTestId("requirement");
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveAttribute("data-satisfied", "true");
    expect(within(rows[0]!).getByRole("link", { name: "buzz-agent@marcus" })).toHaveAttribute("href", "/app/agents/marcus");
    expect(rows[1]).toHaveAttribute("data-satisfied", "false");
    expect(rows[1]).toHaveTextContent("inactive");
    expect(within(rows[1]!).queryByRole("link")).toBeNull();
    expect(rows[2]).toHaveAttribute("data-satisfied", "unknown");
    expect(within(rows[3]!).getByRole("link", { name: "qmd-refresh" })).toHaveAttribute("href", "/app/workflows/qmd-refresh");
    expect(screen.getByText(/nothing requires this workflow/i)).toBeInTheDocument();
  });
  it("lists dependents with their enabled state as links", () => {
    render(<RequiresPanel requires={[]} requiredBy={[toDependent({ workflow: "augustus-content", enabled: true }), toDependent({ workflow: "raw-ingest", enabled: false })]} />);
    expect(screen.getByText(/requires nothing/i)).toBeInTheDocument();
    const rows = screen.getAllByTestId("dependent");
    expect(rows[0]).toHaveAttribute("data-enabled", "true");
    expect(within(rows[0]!).getByRole("link", { name: "augustus-content" })).toHaveAttribute("href", "/app/workflows/augustus-content");
    expect(rows[0]).toHaveTextContent("enabled");
    expect(rows[1]).toHaveAttribute("data-enabled", "false");
    expect(rows[1]).toHaveTextContent("paused");
  });
});
