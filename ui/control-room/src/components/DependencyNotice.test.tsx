import { render, screen } from "@testing-library/react";
import DependencyNotice from "./DependencyNotice";

describe("DependencyNotice", () => {
  it("renders nothing when no enabled dependent and no guards", () => {
    render(<DependencyNotice action="pause" requiredBy={[{ workflow: "raw-ingest", enabled: false }]} guards={null} />);
    expect(screen.queryByTestId("dependency-notice")).toBeNull();
  });
  it("names every enabled dependent", () => {
    render(<DependencyNotice action="stop" requiredBy={[{ workflow: "augustus-content", enabled: true }, { workflow: "raw-ingest", enabled: false }, { workflow: "content-change-dispatch", enabled: true }]} guards={null} />);
    const notice = screen.getByTestId("dependency-notice");
    expect(notice).toHaveTextContent("augustus-content, content-change-dispatch");
    expect(notice).not.toHaveTextContent("raw-ingest");
  });
  it("quotes the guards sentence", () => {
    render(<DependencyNotice action="pause" requiredBy={[]} guards="Without it a failed run is a line in a receipt that reaches nobody." />);
    expect(screen.getByTestId("dependency-notice")).toHaveTextContent("Without it a failed run is a line in a receipt that reaches nobody.");
  });
});
