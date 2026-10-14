import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import CardRunStop from "./CardRunStop";

const applied = { receipt: { receipt_id: "rcpt-1", result: "applied", action: "stop", workflow_id: "board-work@alpha" }, control: { state: "paused", actions: [] } };
const refused = { status: 403, body: { receipt: { result: "refused", refusal: { code: "not_allowlisted", message: "board-work is not listed" } }, error: "refused" } };

describe("CardRunStop", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("names the running unit and stops it with a reason, confirm: true", async () => {
    const { calls } = mockFetch({ "/api/v1/control/actions": applied });
    const onStopped = vi.fn();
    render(<CardRunStop unit="board-work@alpha" onStopped={onStopped} />);
    expect(screen.getByText("board-work@alpha")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
    const confirm = screen.getByRole("button", { name: "Confirm stop" });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "Reason" }), { target: { value: "wrong brief" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(onStopped).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "board-work@alpha", action: "stop", reason: "wrong brief", confirm: true });
  });

  it("a refusal stays on the card with the broker's message", async () => {
    mockFetch({ "/api/v1/control/actions": refused });
    const onStopped = vi.fn();
    render(<CardRunStop unit="board-work@alpha" onStopped={onStopped} />);
    fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Reason" }), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm stop" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("board-work is not listed");
    expect(onStopped).not.toHaveBeenCalled();
  });

  it("cancel posts nothing", () => {
    const { fetchMock } = mockFetch({});
    render(<CardRunStop unit="board-work@alpha" onStopped={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Stop run" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
