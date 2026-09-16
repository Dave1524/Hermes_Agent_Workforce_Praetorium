import { render, screen } from "@testing-library/react";
import GuardsChip from "./GuardsChip";

describe("GuardsChip", () => {
  it("renders nothing without a guards sentence", () => {
    render(<GuardsChip guards={null} />);
    expect(screen.queryByTestId("guards-chip")).toBeNull();
  });
  it("carries the sentence as its title", () => {
    render(<GuardsChip guards="Without it a hand edit under /etc is caught by nothing." />);
    const chip = screen.getByTestId("guards-chip");
    expect(chip).toHaveTextContent("guards");
    expect(chip).toHaveAttribute("title", "Without it a hand edit under /etc is caught by nothing.");
  });
});
