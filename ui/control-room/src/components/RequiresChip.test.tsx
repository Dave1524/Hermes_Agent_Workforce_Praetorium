import { render, screen } from "@testing-library/react";
import { toRequirement } from "@/model/requires";
import RequiresChip from "./RequiresChip";

const up = toRequirement({ unit: "buzz-agent@marcus", scope: "user", state: "active", satisfied: true });
const down = toRequirement({ unit: "ollama.service", scope: "system", state: "inactive", satisfied: false });
const unknown = toRequirement({ unit: "buzz-notion-broker", scope: "user", state: "unknown", satisfied: null });

describe("RequiresChip", () => {
  it("renders nothing when a workflow requires nothing", () => {
    render(<RequiresChip requires={[]} />);
    expect(screen.queryByTestId("requires-chip")).toBeNull();
  });
  it.each([
    [[up], "satisfied", "requires ok"],
    [[up, down, { ...down, unit: "later" }], "down", "requires down: ollama.service"],
    [[up, unknown], "unknown", "requires unknown"],
  ])("renders %o as %s", (rows, status, text) => {
    render(<RequiresChip requires={rows} />);
    const chip = screen.getByTestId("requires-chip");
    expect(chip).toHaveAttribute("data-requires", status);
    expect(chip).toHaveTextContent(text);
    expect(chip).toHaveAttribute("title", expect.stringContaining("buzz-agent@marcus: active"));
  });
});
