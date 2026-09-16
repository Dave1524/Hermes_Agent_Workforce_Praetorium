import { act, renderHook } from "@testing-library/react";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { type RuntimeActionId } from "@/api/schemas/control";
import { triggerChoices, useControlAction } from "./useControlAction";

const control = { state: "paused", actions: [] };
const previewed = { receipt: { receipt_id: "rcpt-1", result: "previewed", action: "resume", stage: "preview" }, control, preview: { preview_token: "rcpt-1", implication: { catchUp: true, message: "will catch up" } } };
const applied = { receipt: { receipt_id: "rcpt-2", result: "applied", action: "resume", stage: "apply", after: { state: "active" }, next_scheduled_run: "2026-09-16T03:00:00Z" }, control: { ...control, state: "active" } };

describe("useControlAction", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("resume is two-stage: preview yields the token, apply carries it", async () => {
    const { calls } = mockFetch({ "/api/v1/control/actions": [previewed, applied] });
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "resume", stage: "preview", reason: "first live resume" });
    });
    expect(result.current.state.phase).toBe("previewed");
    const state = result.current.state;
    if (state.phase !== "previewed") throw new Error("expected previewed");
    expect(state.previewToken).toBe("rcpt-1");
    expect(state.implication?.catchUp).toBe(true);
    await act(async () => {
      await result.current.send({ action: "resume", stage: "apply", preview_token: state.previewToken, reason: "first live resume" });
    });
    expect(result.current.state.phase).toBe("applied");
    expect(JSON.parse(String(calls[1]!.init?.body))).toEqual({ workflow_id: "raw-ingest", action: "resume", stage: "apply", preview_token: "rcpt-1", reason: "first live resume" });
  });

  it("stop refuses client-side without a reason and never posts; with one it sends confirm: true", async () => {
    const { fetchMock, calls } = mockFetch({ "/api/v1/control/actions": applied });
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "stop", reason: "   " });
    });
    expect(result.current.state).toMatchObject({ phase: "refused", status: 0, refusal: { code: "reason_required" } });
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => {
      await result.current.send({ action: "stop", reason: "runaway" });
    });
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "raw-ingest", action: "stop", reason: "runaway", confirm: true });
  });

  it.each<[RuntimeActionId, string]>([
    ["stop", "reason_required"],
    ["restart", "reason_required"],
  ])("%s on a runtime refuses client-side without a reason -> %s, nothing posted", async (action, code) => {
    const { fetchMock } = mockFetch({ "/api/v1/control/actions": applied });
    const { result } = renderHook(() => useControlAction("buzz-agent@marcus"));
    await act(async () => {
      await result.current.send({ action, reason: "" });
    });
    expect(result.current.state).toMatchObject({ phase: "refused", status: 0, refusal: { code } });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each<[RuntimeActionId, string | undefined, Record<string, unknown>]>([
    ["start", undefined, { workflow_id: "buzz-agent@marcus", action: "start", confirm: true }],
    ["start", "after the .env edit", { workflow_id: "buzz-agent@marcus", action: "start", reason: "after the .env edit", confirm: true }],
    ["restart", "prompt changed", { workflow_id: "buzz-agent@marcus", action: "restart", reason: "prompt changed", confirm: true }],
  ])("%s with reason %s posts confirm: true — the broker's confirmation_required gate is met by the dialog", async (action, reason, body) => {
    const { calls } = mockFetch({ "/api/v1/control/actions": applied });
    const { result } = renderHook(() => useControlAction("buzz-agent@marcus"));
    await act(async () => {
      await result.current.send(reason === undefined ? { action } : { action, reason });
    });
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual(body);
  });

  it("a trigger_required refusal exposes its choices", async () => {
    mockFetch({ "/api/v1/control/actions": { status: 400, body: { receipt: { result: "refused", refusal: { code: "trigger_required", message: "name one", choices: ["a.timer", "b.timer"] } }, control, error: "name one" } } });
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "run_now" });
    });
    expect(result.current.state.phase).toBe("refused");
    expect(triggerChoices(result.current.state)).toEqual(["a.timer", "b.timer"]);
  });

  it.each([
    [403, { receipt: { result: "refused", refusal: { code: "peer_denied", message: "no" } }, control, error: "no" }, "refused"],
    [404, { error: "workflow not found" }, "failed"],
    [500, { receipt: { result: "failed", commands: [] }, control, error: "the broker's command failed; see receipt.commands" }, "failed"],
    [502, { error: "control broker unreachable: x", receipt: null }, "failed"],
    [504, { error: "control broker unreachable: timeout", receipt: null }, "failed"],
  ])("HTTP %d -> %s is a visible state", async (status, body, phase) => {
    mockFetch({ "/api/v1/control/actions": { status, body } });
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "pause" });
    });
    expect(result.current.state.phase).toBe(phase);
    expect(result.current.state).toMatchObject({ status });
  });

  it("a non-JSON 502 is failed, not thrown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Bad Gateway", { status: 502 })));
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "pause" });
    });
    expect(result.current.state).toMatchObject({ phase: "failed", status: 502 });
  });

  it("retry forwards retry_of", async () => {
    const { calls } = mockFetch({ "/api/v1/control/actions": applied });
    const { result } = renderHook(() => useControlAction("raw-ingest"));
    await act(async () => {
      await result.current.send({ action: "retry", retry_of: "run-0913" });
    });
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ workflow_id: "raw-ingest", action: "retry", retry_of: "run-0913" });
  });
});
