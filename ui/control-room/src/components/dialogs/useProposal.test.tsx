import { act, renderHook } from "@testing-library/react";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { pinnedOnlyBlockers, useProposal } from "./useProposal";

const control = { state: "paused", actions: [] };
const basePreview = {
  stage: "preview", proposal_id: "p-1", preview_token: "tok-1", expires_at: "2026-09-14T08:10:00Z", base: "main", branch: "control-room/raw-ingest-schedule",
  summary: "raw-ingest: OnCalendar=daily", description: { on_calendar: ["daily"] }, files: ["systemd/raw-ingest.timer"], diff: "--- a\n+++ b", diff_sha256: "abc",
  checks: [{ id: "toml", class: "structural", status: "pass", output: "" }], residue: null, retention: null, submit_allowed: true, submit_blockers: [], control, record: {},
};
const proposed = { on_calendar: ["daily"], randomized_delay_sec: null, persistent: null, trigger: null };

describe("useProposal", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("preview then submit forwards reason, proposed and the preview token", async () => {
    const submitted = { stage: "submitted", proposal_id: "p-1", pr: { url: "https://github.com/x/y/pull/9", number: 9, branch: "b", draft: false }, diff_sha256: "abc", control };
    const { calls } = mockFetch({ "/api/v1/control/proposals": [basePreview, submitted] });
    const { result } = renderHook(() => useProposal("raw-ingest", "schedule"));
    await act(async () => {
      await result.current.preview({ reason: "move earlier", proposed });
    });
    expect(result.current.state.phase).toBe("previewed");
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "raw-ingest", kind: "schedule", stage: "preview", reason: "move earlier", proposed, preview_token: null });
    await act(async () => {
      await result.current.submit(false);
    });
    expect(result.current.state).toMatchObject({ phase: "submitted", submitted: { pr: { url: "https://github.com/x/y/pull/9", number: 9 } } });
    expect(JSON.parse(String(calls[1]!.init?.body))).toEqual({ workflow_id: "raw-ingest", kind: "schedule", stage: "submit", reason: "move earlier", proposed, preview_token: "tok-1" });
  });

  it("submit is refused client-side when submit_allowed is false and blockers are not pinned-only", async () => {
    const { fetchMock } = mockFetch({ "/api/v1/control/proposals": { ...basePreview, submit_allowed: false, submit_blockers: ["structural check failed"], checks: [{ id: "toml", class: "structural", status: "fail", output: "bad" }] } });
    const { result } = renderHook(() => useProposal("raw-ingest", "schedule"));
    await act(async () => {
      await result.current.preview({ reason: "x", proposed });
    });
    expect(result.current.canSubmit(false)).toBe(false);
    expect(result.current.canSubmit(true)).toBe(false);
    await act(async () => {
      await result.current.submit(true);
    });
    expect(result.current.state).toMatchObject({ phase: "refused", error: { code: "submit_blocked" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("pinned-only blockers unlock submit once acknowledged, and the flag travels in proposed", async () => {
    const pinned = { ...basePreview, submit_allowed: false, submit_blockers: ["pinned suite fails"], checks: [{ id: "tests", class: "pinned", status: "fail", output: "red" }, { id: "toml", class: "structural", status: "pass", output: "" }] };
    const submitted = { stage: "submitted", proposal_id: "p-1", pr: { url: "u", number: 10, branch: "b", draft: true }, control };
    const { calls } = mockFetch({ "/api/v1/control/proposals": [pinned, submitted] });
    const { result } = renderHook(() => useProposal("raw-ingest", "retire"));
    await act(async () => {
      await result.current.preview({ reason: "done", proposed: { artifact_retention: { receipts: "keep", notion: "keep", inbox: "keep", note: "" }, acknowledge_pinned_tests: false } });
    });
    const state = result.current.state;
    if (state.phase !== "previewed") throw new Error("expected previewed");
    expect(pinnedOnlyBlockers(state.preview)).toBe(true);
    expect(result.current.canSubmit(false)).toBe(false);
    expect(result.current.canSubmit(true)).toBe(true);
    await act(async () => {
      await result.current.submit(true);
    });
    expect(result.current.state.phase).toBe("submitted");
    expect(JSON.parse(String(calls[1]!.init?.body)).proposed.acknowledge_pinned_tests).toBe(true);
  });

  it("a refusal body is a refused state with code, message and choices", async () => {
    mockFetch({ "/api/v1/control/proposals": { status: 400, body: { error: { code: "trigger_required", message: "name one", choices: ["a", "b"] }, record: {}, control } } });
    const { result } = renderHook(() => useProposal("raw-ingest", "schedule"));
    await act(async () => {
      await result.current.preview({ reason: "x", proposed });
    });
    expect(result.current.state).toMatchObject({ phase: "refused", status: 400, error: { code: "trigger_required", choices: ["a", "b"] } });
  });

  it("list yields the workflow's proposals", async () => {
    mockFetch({ "/api/v1/control/proposals": { stage: "list", items: [{ proposal_id: "p-0", kind: "schedule", stage: "submitted", pr: { url: "u", number: 3 } }] } });
    const { result } = renderHook(() => useProposal("raw-ingest", "schedule"));
    let items: unknown = null;
    await act(async () => {
      items = await result.current.list();
    });
    expect(items).toEqual([{ proposal_id: "p-0", kind: "schedule", stage: "submitted", pr: { url: "u", number: 3 } }]);
  });
});
