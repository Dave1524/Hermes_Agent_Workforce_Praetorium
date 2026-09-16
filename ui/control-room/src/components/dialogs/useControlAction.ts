import { useCallback, useState } from "react";
import { ApiError, postControl } from "@/api/client";
import type { ControlRequest, ControlResponse, Implication, Refusal } from "@/api/schemas/control";

export type ControlState =
  | { phase: "idle" }
  | { phase: "busy" }
  | { phase: "previewed"; status: number; response: ControlResponse; previewToken: string; implication: Implication | null }
  | { phase: "applied"; status: number; response: ControlResponse }
  | { phase: "refused"; status: number; response: ControlResponse | null; refusal: Refusal }
  | { phase: "failed"; status: number; response: ControlResponse | null; message: string };

export type ControlSend = Omit<ControlRequest, "workflow_id">;

export interface ControlActionApi {
  state: ControlState;
  send: (request: ControlSend) => Promise<ControlState>;
  reset: () => void;
}

const IDLE: ControlState = { phase: "idle" };

const classify = (status: number, response: ControlResponse): ControlState => {
  const receipt = response.receipt;
  if (receipt?.result === "previewed" && response.preview?.preview_token) {
    return { phase: "previewed", status, response, previewToken: response.preview.preview_token, implication: response.preview.implication ?? null };
  }
  if (receipt?.result === "applied") return { phase: "applied", status, response };
  if (receipt?.result === "refused" && receipt.refusal) return { phase: "refused", status, response, refusal: receipt.refusal };
  return { phase: "failed", status, response, message: response.error ?? `HTTP ${status}` };
};

const failed = (e: unknown): ControlState => {
  if (e instanceof ApiError) return { phase: "failed", status: e.status, response: null, message: e.message };
  return { phase: "failed", status: 0, response: null, message: e instanceof Error ? e.message : String(e) };
};

// The stop rule is the broker's (reason_required); refusing before the POST just saves a round trip.
const guard = (request: ControlSend): ControlState | null => {
  if (request.action === "stop" && !(request.reason ?? "").trim()) {
    return { phase: "refused", status: 0, response: null, refusal: { code: "reason_required", message: "stop needs a non-empty reason" } };
  }
  return null;
};

const withConfirm = (request: ControlSend): ControlSend => (request.action === "stop" ? { ...request, confirm: true } : request);

export const useControlAction = (workflowId: string): ControlActionApi => {
  const [state, setState] = useState<ControlState>(IDLE);
  const send = useCallback(
    async (request: ControlSend): Promise<ControlState> => {
      const early = guard(request);
      if (early) {
        setState(early);
        return early;
      }
      setState({ phase: "busy" });
      const next = await postControl({ workflow_id: workflowId, ...withConfirm(request) })
        .then(({ status, body }) => classify(status, body))
        .catch(failed);
      setState(next);
      return next;
    },
    [workflowId],
  );
  const reset = useCallback(() => setState(IDLE), []);
  return { state, send, reset };
};

export const triggerChoices = (state: ControlState): string[] | null =>
  state.phase === "refused" && state.refusal.code === "trigger_required" ? (state.refusal.choices ?? []) : null;
