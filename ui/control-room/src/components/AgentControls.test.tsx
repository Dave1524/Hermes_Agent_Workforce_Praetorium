import { fireEvent, render, screen } from "@testing-library/react";
import { agentDown, agentPaused, agentUp } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { toAgent } from "@/model/agent";
import AgentControls from "./AgentControls";

const buttons = () => ({
  start: screen.getByRole("button", { name: "Start agent now" }),
  stop: screen.getByRole("button", { name: "Stop agent now" }),
  restart: screen.getByRole("button", { name: "Restart agent now" }),
});

describe("AgentControls", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("an active runtime offers Stop and Restart; Start is disabled with the broker's reason as tooltip", () => {
    render(<AgentControls agent={toAgent(agentUp)} onChanged={() => {}} />);
    const b = buttons();
    expect(b.start).toBeDisabled();
    expect(b.start).toHaveAttribute("title", "runtime is active, not paused");
    expect(b.stop).toBeEnabled();
    expect(b.restart).toBeEnabled();
    expect(b.stop).not.toHaveAttribute("title");
  });

  it("a fleet-off runtime offers Start only", () => {
    render(<AgentControls agent={toAgent(agentPaused)} onChanged={() => {}} />);
    const b = buttons();
    expect(b.start).toBeEnabled();
    expect(b.stop).toBeDisabled();
    expect(b.restart).toBeDisabled();
    expect(b.restart).toHaveAttribute("title", "runtime is paused, not active");
  });

  it("with the bus unavailable every verb is disabled and says so", () => {
    render(<AgentControls agent={toAgent(agentDown)} onChanged={() => {}} />);
    const b = buttons();
    for (const button of [b.start, b.stop, b.restart]) {
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("title", "systemd state unavailable");
    }
  });

  it("without a control block there is no button and the panel says so", () => {
    render(<AgentControls agent={toAgent({ ...agentPaused, control: null })} onChanged={() => {}} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/No runtime actions offered/)).toBeInTheDocument();
  });

  it("opens the dialog for the clicked verb and closes it on Cancel without posting", () => {
    const { fetchMock } = mockFetch({});
    render(<AgentControls agent={toAgent(agentPaused)} onChanged={() => {}} />);
    fireEvent.click(buttons().start);
    expect(screen.getByRole("dialog", { name: "Start agent now: trajan" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders the last control action receipt when the control carries one", () => {
    const lastAction = { receipt_id: "rcpt-3", result: "refused", action: "restart", workflow_id: "buzz-agent@marcus", refusal: { code: "confirmation_required", message: "restart needs confirm" }, links: { agent: "/agents/marcus" } };
    render(<AgentControls agent={toAgent({ ...agentUp, control: { ...agentUp.control!, lastAction } })} onChanged={() => {}} />);
    expect(screen.getByTestId("receipt")).toHaveAttribute("data-result", "refused");
    expect(screen.getByTestId("receipt")).toHaveTextContent("confirmation_required");
  });
});
