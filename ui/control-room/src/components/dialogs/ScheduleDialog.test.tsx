import { fireEvent, render, screen } from "@testing-library/react";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import ScheduleDialog from "./ScheduleDialog";

const control = { state: "paused", actions: [] };
const preview = (over: Record<string, unknown>) => ({
  stage: "preview", proposal_id: "p-1", preview_token: "tok-1", expires_at: "2026-09-14T08:10:00Z", base: "main", branch: "control-room/raw-ingest-schedule",
  summary: "raw-ingest: OnCalendar=daily", description: { on_calendar: ["daily"] }, files: ["systemd/raw-ingest.timer"], diff: "-OnCalendar=Tue..Sat 03:00\n+OnCalendar=daily", diff_sha256: "abc",
  checks: [{ id: "unit-syntax", class: "structural", status: "pass", output: "" }], residue: null, retention: null, submit_allowed: true, submit_blockers: [], control, record: {},
  ...over,
});
const timers = [{ unit: "raw-ingest.timer", kind: "timer" }];

const fillAndPreview = () => {
  fireEvent.change(screen.getByLabelText(/OnCalendar/), { target: { value: "daily" } });
  fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "run every day" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
};

describe("ScheduleDialog", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("previews, then opens the pull request only when submit_allowed", async () => {
    const submitted = { stage: "submitted", proposal_id: "p-1", pr: { url: "https://github.com/x/y/pull/9", number: 9, branch: "b", draft: false }, diff_sha256: "abc", control };
    const { calls } = mockFetch({ "/api/v1/control/proposals": [preview({}), submitted] });
    render(<ScheduleDialog workflowId="raw-ingest" workflowName="raw-ingest" timers={timers} onClose={() => {}} onChanged={() => {}} />);
    expect(screen.queryByRole("button", { name: /open pull request/i })).toBeNull();
    fillAndPreview();
    await screen.findByText("raw-ingest: OnCalendar=daily");
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "raw-ingest", kind: "schedule", stage: "preview", reason: "run every day", proposed: { on_calendar: ["daily"], randomized_delay_sec: null, persistent: null, trigger: null }, preview_token: null });
    const open = screen.getByRole("button", { name: /open pull request/i });
    expect(open).toBeEnabled();
    fireEvent.click(open);
    await screen.findByRole("link", { name: /pull request #9/i });
    expect(JSON.parse(String(calls[1]!.init?.body))).toMatchObject({ stage: "submit", preview_token: "tok-1" });
  });

  it("a structural failure keeps the pull request button disabled and names the blocker", async () => {
    const { calls } = mockFetch({ "/api/v1/control/proposals": preview({ submit_allowed: false, submit_blockers: ["unit-syntax failed"], checks: [{ id: "unit-syntax", class: "structural", status: "fail", output: "bad OnCalendar" }] }) });
    render(<ScheduleDialog workflowId="raw-ingest" workflowName="raw-ingest" timers={timers} onClose={() => {}} onChanged={() => {}} />);
    fillAndPreview();
    await screen.findByText("unit-syntax failed");
    expect(screen.getByRole("button", { name: /open pull request/i })).toBeDisabled();
    expect(screen.queryByLabelText(/acknowledge/i)).toBeNull();
    expect(calls).toHaveLength(1);
  });

  it("a pinned-only failure unlocks the pull request through the acknowledge checkbox, as a draft", async () => {
    mockFetch({ "/api/v1/control/proposals": preview({ submit_allowed: false, submit_blockers: ["pinned suite fails"], checks: [{ id: "tests", class: "pinned", status: "fail", output: "red" }] }) });
    render(<ScheduleDialog workflowId="raw-ingest" workflowName="raw-ingest" timers={timers} onClose={() => {}} onChanged={() => {}} />);
    fillAndPreview();
    const ack = await screen.findByLabelText(/acknowledge/i);
    expect(screen.getByRole("button", { name: /open pull request/i })).toBeDisabled();
    fireEvent.click(ack);
    expect(screen.getByRole("button", { name: /open pull request/i })).toBeEnabled();
    expect(screen.getByText(/opens as a draft/i)).toBeInTheDocument();
  });

  it("the trigger select appears only with two or more timers", () => {
    mockFetch({});
    const { unmount } = render(<ScheduleDialog workflowId="w" workflowName="w" timers={timers} onClose={() => {}} onChanged={() => {}} />);
    expect(screen.queryByLabelText(/^Trigger/)).toBeNull();
    unmount();
    render(<ScheduleDialog workflowId="w" workflowName="w" timers={[...timers, { unit: "w-2.timer", kind: "timer" }]} onClose={() => {}} onChanged={() => {}} />);
    expect(screen.getByLabelText(/^Trigger/)).toBeInTheDocument();
  });
});
