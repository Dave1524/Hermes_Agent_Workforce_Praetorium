import { render, screen } from "@testing-library/react";
import { lastActionSchema } from "@/api/schemas/workflow";
import LastActionPanel from "./LastActionPanel";

// Verbatim from the live API (GET /api/v1/workflows/knowledge-digest, 2026-09-16): the seam
// shape, which is not the receipt shape — before/after are strings.
const liveSeam = {
  action: "pause",
  actor: "dave via control-room from 100.125.209.101",
  reason: "",
  at: "2026-09-15T10:34:02Z",
  result: "applied",
  refusal: null,
  note: null,
  before: "active",
  after: "paused",
  receiptId: "20260915T103402Z-pause-eb964f",
  links: { receipt: "/var/lib/control-room/receipts/knowledge-digest/20260915T103402Z-pause-eb964f.json", run: null, previewReceipt: null, workflow: "/workflows/knowledge-digest" },
};

describe("LastActionPanel", () => {
  it("accepts the live seam shape and renders result, action, states, actor and receipt id", () => {
    expect(lastActionSchema.safeParse(liveSeam).success).toBe(true);
    render(<LastActionPanel lastAction={lastActionSchema.parse(liveSeam)} />);
    const panel = screen.getByTestId("last-action");
    expect(panel).toHaveAttribute("data-result", "applied");
    expect(panel).toHaveTextContent("pause");
    expect(panel).toHaveTextContent(/active → paused/);
    expect(panel).toHaveTextContent("dave via control-room from 100.125.209.101");
    expect(panel).toHaveTextContent("20260915T103402Z-pause-eb964f");
  });
  it("names the refusal code and the note when the receipt carries them", () => {
    render(<LastActionPanel lastAction={{ ...liveSeam, action: "restart", result: "refused", refusal: "confirmation_required", before: "active", after: null, note: "restart needs confirm" }} />);
    expect(screen.getByTestId("last-action")).toHaveAttribute("data-result", "refused");
    expect(screen.getByTestId("last-action")).toHaveTextContent("confirmation_required");
    expect(screen.getByTestId("last-action")).toHaveTextContent(/active → —/);
    expect(screen.getByTestId("last-action")).toHaveTextContent("restart needs confirm");
  });
  it("says so when there is none", () => {
    render(<LastActionPanel lastAction={null} />);
    expect(screen.getByText("No control action recorded.")).toBeInTheDocument();
  });
});
