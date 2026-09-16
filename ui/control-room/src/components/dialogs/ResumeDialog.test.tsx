import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import ResumeDialog from "./ResumeDialog";

const control = { state: "paused", actions: [] };
const previewed = {
  receipt: { receipt_id: "rcpt-1", result: "previewed", action: "resume", stage: "preview", before: { state: "paused" }, after: { state: "paused" } },
  control,
  preview: { preview_token: "rcpt-1", implication: { persistent: true, catchUp: true, lastTriggerAt: "2026-09-13T03:00:00Z", missedElapseAt: "2026-09-14T03:00:00Z", nextElapseAt: "2026-09-16T03:00:00Z", approximate: false, message: "Persistent=true and the last elapse was missed: enabling fires the service now." } },
};
const applied = { receipt: { receipt_id: "rcpt-2", result: "applied", action: "resume", stage: "apply", before: { state: "paused" }, after: { state: "active" }, next_scheduled_run: "2026-09-16T03:00:00Z" }, control: { ...control, state: "active" } };

describe("ResumeDialog", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the implication before Apply and applies with the preview token", async () => {
    const { calls } = mockFetch({ "/api/v1/control/actions": [previewed, applied] });
    const onChanged = vi.fn();
    render(<ResumeDialog workflowId="raw-ingest" workflowName="raw-ingest" onClose={() => {}} onChanged={onChanged} />);

    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    const implication = await screen.findByTestId("implication");
    expect(implication).toHaveAttribute("data-catch-up", "true");
    expect(implication).toHaveTextContent(/Catch-up WILL fire/);
    expect(implication).toHaveTextContent(/enabling fires the service now/);
    expect(calls).toHaveLength(1);
    expect(onChanged).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /apply with this preview/i }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(calls[1]!.init?.body))).toMatchObject({ action: "resume", stage: "apply", preview_token: "rcpt-1" });
    expect(screen.getByTestId("receipt")).toHaveAttribute("data-result", "applied");
    expect(screen.getByTestId("receipt")).toHaveTextContent(/paused → active/);
  });

  it("a stale preview is shown as a refusal, not applied", async () => {
    const stale = { status: 400, body: { receipt: { result: "refused", refusal: { code: "preview_stale", message: "preview expired" } }, control, error: "preview expired" } };
    mockFetch({ "/api/v1/control/actions": [previewed, stale] });
    const onChanged = vi.fn();
    render(<ResumeDialog workflowId="raw-ingest" workflowName="raw-ingest" onClose={() => {}} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByTestId("implication");
    fireEvent.click(screen.getByRole("button", { name: /apply with this preview/i }));
    const refusal = await screen.findByTestId("refusal");
    expect(refusal).toHaveTextContent(/preview_stale/);
    expect(refusal).toHaveTextContent(/HTTP 400/);
    expect(onChanged).not.toHaveBeenCalled();
  });
});
