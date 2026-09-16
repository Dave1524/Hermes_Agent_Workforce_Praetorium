import { render, screen } from "@testing-library/react";
import PauseDialog from "./PauseDialog";
import StopDialog from "./StopDialog";

const base = { workflowId: "buzz-agent@augustus", workflowName: "buzz-agent@augustus", onClose: () => {}, onChanged: () => {} };

describe("PauseDialog and StopDialog dependency notice", () => {
  it("shows no notice when nothing enabled depends on the workflow and it guards nothing", () => {
    render(<PauseDialog {...base} requiredBy={[{ workflow: "augustus-content", enabled: false }]} guards={null} />);
    expect(screen.queryByTestId("dependency-notice")).toBeNull();
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
  });
  it("shows the notice with an enabled dependent and still offers Pause", () => {
    render(<PauseDialog {...base} requiredBy={[{ workflow: "augustus-content", enabled: true }]} guards={null} />);
    expect(screen.getByTestId("dependency-notice")).toHaveTextContent("augustus-content");
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
  });
  it("shows the guards sentence in the Stop dialog and does not block on it", () => {
    render(<StopDialog {...base} workflowId="workflow-incidents" workflowName="workflow-incidents" requiredBy={[]} guards="Without it a failed run is a line in a receipt that reaches nobody." />);
    expect(screen.getByTestId("dependency-notice")).toHaveTextContent("Without it a failed run");
    expect(screen.getByRole("button", { name: /stop the running service/i })).toBeDisabled();
  });
});
