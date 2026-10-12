import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import ScopePicker from "./ScopePicker";

function Harness({ start = "" }: { start?: string }) {
  const [value, setValue] = useState(start);
  return (
    <>
      <ScopePicker value={value} onChange={setValue} />
      <output data-testid="value">{value}</output>
    </>
  );
}

const input = () => screen.getByLabelText("Scope");
const value = () => screen.getByTestId("value").textContent;

describe("ScopePicker", () => {
  it("filters suggestions as you type and adds one by click", () => {
    render(<Harness />);
    fireEvent.focus(input());
    fireEvent.change(input(), { target: { value: "trading" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["repo:AI_Trading_Bot"]);
    fireEvent.mouseDown(screen.getByRole("option"));
    expect(value()).toBe("repo:AI_Trading_Bot");
  });

  it("takes a typed value of the right shape on Enter, and refuses a malformed one", () => {
    render(<Harness />);
    fireEvent.change(input(), { target: { value: "vault:05_knowledge/research" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(value()).toBe("vault:05_knowledge/research");
    fireEvent.change(input(), { target: { value: "nonsense" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(value()).toBe("vault:05_knowledge/research");
  });

  it("removes a chip and hides what is already chosen", () => {
    render(<Harness start="vault:05_knowledge, repo:energy-ledger" />);
    fireEvent.click(screen.getByRole("button", { name: "Remove repo:energy-ledger" }));
    expect(value()).toBe("vault:05_knowledge");
    fireEvent.focus(input());
    expect(screen.queryByRole("option", { name: "vault:05_knowledge" })).toBeNull();
  });
});
