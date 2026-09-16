import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { agentPaused, agentUp } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { toAgent } from "@/model/agent";
import RuntimeDialog from "./RuntimeDialog";

const applied = (action: string, state: string) => ({
  receipt: { receipt_id: "rcpt-9", result: "applied", action, workflow_id: "buzz-agent@marcus", after: { state }, links: { agent: "/agents/marcus" } },
  control: { state, actions: [] },
});
const refused = { status: 400, body: { receipt: { result: "refused", refusal: { code: "state_conflict", message: "buzz-agent@marcus is already active" } }, control: { state: "active", actions: [] }, error: "already active" } };

describe("RuntimeDialog", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("start: reason optional, names the double-hosting risk and check-loaded.sh, posts confirm: true, applied re-fetches", async () => {
    const { calls } = mockFetch({ "/api/v1/control/actions": applied("start", "active") });
    const onChanged = vi.fn();
    render(<RuntimeDialog action="start" agent={toAgent(agentPaused)} unit="buzz-agent@trajan" onClose={() => {}} onChanged={onChanged} />);
    expect(screen.getByRole("dialog", { name: "Start agent now: trajan" })).toBeInTheDocument();
    expect(screen.getByText(/Buzz Desktop on the Mac is also hosting/)).toBeInTheDocument();
    expect(screen.getAllByText(/check-loaded\.sh/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("boot-policy")).toHaveTextContent("Unit file disabled: this changes the session only");
    expect(screen.queryByTestId("dependency-notice")).toBeNull();
    const button = screen.getByRole("button", { name: "Start agent now" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "buzz-agent@trajan", action: "start", confirm: true });
    expect(screen.getByTestId("receipt")).toHaveAttribute("data-result", "applied");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it.each<["stop" | "restart", RegExp]>([
    ["stop", /Stopping this refuses every run of/],
    ["restart", /Restarting this refuses every run of/],
  ])("%s: reason required, dependents named as a notice, a turn in progress is lost, boot policy stated", async (action, notice) => {
    const { calls } = mockFetch({ "/api/v1/control/actions": applied(action, action === "stop" ? "paused" : "active") });
    const onChanged = vi.fn();
    render(<RuntimeDialog action={action} agent={toAgent(agentUp)} unit="buzz-agent@marcus" onClose={() => {}} onChanged={onChanged} />);
    const label = action === "stop" ? "Stop agent now" : "Restart agent now";
    expect(screen.getByRole("button", { name: label })).toBeDisabled();
    expect(screen.getByText(/A turn in progress is lost/)).toBeInTheDocument();
    expect(screen.getByTestId("dependency-notice")).toHaveTextContent(notice);
    expect(screen.getByTestId("dependency-notice")).toHaveTextContent("agent-inbox-sync");
    expect(screen.getByTestId("boot-policy")).toHaveTextContent("Unit file enabled: this runtime also comes back after a reboot");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "prompt changed" } });
    fireEvent.click(screen.getByRole("button", { name: label }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "buzz-agent@marcus", action, reason: "prompt changed", confirm: true });
  });

  it("cancel posts nothing", () => {
    const { fetchMock } = mockFetch({});
    const onClose = vi.fn();
    render(<RuntimeDialog action="start" agent={toAgent(agentPaused)} unit="buzz-agent@trajan" onClose={onClose} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a broker refusal is rendered with its code and does not re-fetch", async () => {
    mockFetch({ "/api/v1/control/actions": refused });
    const onChanged = vi.fn();
    render(<RuntimeDialog action="start" agent={toAgent(agentUp)} unit="buzz-agent@marcus" onClose={() => {}} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Start agent now" }));
    await waitFor(() => expect(screen.getByTestId("refusal")).toHaveTextContent("state_conflict"));
    expect(screen.getByTestId("refusal")).toHaveTextContent("already active");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("states an unknown boot policy as unknown rather than inventing one", () => {
    mockFetch({});
    const agent = toAgent({ ...agentUp, runtime: { ...agentUp.runtime, unitFileState: null } });
    render(<RuntimeDialog action="stop" agent={agent} unit="buzz-agent@marcus" onClose={() => {}} onChanged={() => {}} />);
    expect(screen.getByTestId("boot-policy")).toHaveTextContent("Boot policy unknown");
  });
});
