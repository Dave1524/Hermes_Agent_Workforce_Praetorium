import { useCallback, useState } from "react";
import { ApiError, postProposal } from "@/api/client";
import type { ProposalKind, ProposalPreview, ProposalRecord, ProposalResponse, ProposalSubmitted, RetireProposed, ScheduleProposed } from "@/api/schemas/proposals";

export interface ProposalRefusalError {
  code: string;
  message: string;
  choices: string[] | null;
  diff: string | null;
}

export type ProposalState =
  | { phase: "idle" }
  | { phase: "busy" }
  | { phase: "previewed"; status: number; preview: ProposalPreview; input: ProposalInput }
  | { phase: "submitted"; status: number; submitted: ProposalSubmitted }
  | { phase: "refused"; status: number; error: ProposalRefusalError }
  | { phase: "failed"; status: number; message: string };

export interface ProposalInput {
  reason: string;
  proposed: ScheduleProposed | RetireProposed;
}

export interface ProposalApi {
  state: ProposalState;
  preview: (input: ProposalInput) => Promise<ProposalState>;
  submit: (acknowledgePinned: boolean) => Promise<ProposalState>;
  canSubmit: (acknowledgePinned: boolean) => boolean;
  list: () => Promise<ProposalRecord[]>;
  reset: () => void;
}

const IDLE: ProposalState = { phase: "idle" };

// Mirrors bin/control_room_ui/proposals.js: the acknowledge box only unlocks a preview whose sole failing checks are pinned suites.
export const pinnedOnlyBlockers = (preview: ProposalPreview): boolean =>
  !preview.submit_allowed &&
  preview.checks.some((c) => c.class === "pinned" && c.status === "fail") &&
  preview.checks.every((c) => c.status !== "fail" || c.class === "pinned");

const refusalOf = (body: Extract<ProposalResponse, { error: unknown }>): ProposalRefusalError => {
  if (typeof body.error === "string") return { code: "failed", message: body.error, choices: null, diff: null };
  return { code: body.error.code, message: body.error.message ?? body.error.code, choices: body.error.choices ?? null, diff: body.error.diff ?? null };
};

const classify = (status: number, body: ProposalResponse, input: ProposalInput | null): ProposalState => {
  if ("stage" in body && body.stage === "preview") return input ? { phase: "previewed", status, preview: body, input } : { phase: "failed", status, message: "preview without input" };
  if ("stage" in body && body.stage === "submitted") return { phase: "submitted", status, submitted: body };
  if ("stage" in body && body.stage === "list") return { phase: "failed", status, message: "unexpected list response" };
  return { phase: "refused", status, error: refusalOf(body) };
};

const failed = (e: unknown): ProposalState => {
  if (e instanceof ApiError) return { phase: "failed", status: e.status, message: e.message };
  return { phase: "failed", status: 0, message: e instanceof Error ? e.message : String(e) };
};

export const useProposal = (workflowId: string, kind: ProposalKind): ProposalApi => {
  const [state, setState] = useState<ProposalState>(IDLE);

  const preview = useCallback(
    async (input: ProposalInput): Promise<ProposalState> => {
      setState({ phase: "busy" });
      const next = await postProposal({ workflow_id: workflowId, kind, stage: "preview", reason: input.reason, proposed: input.proposed, preview_token: null })
        .then(({ status, body }) => classify(status, body, input))
        .catch(failed);
      setState(next);
      return next;
    },
    [workflowId, kind],
  );

  const canSubmit = useCallback(
    (acknowledgePinned: boolean): boolean =>
      state.phase === "previewed" && (state.preview.submit_allowed || (acknowledgePinned && pinnedOnlyBlockers(state.preview))),
    [state],
  );

  const submit = useCallback(
    async (acknowledgePinned: boolean): Promise<ProposalState> => {
      if (state.phase !== "previewed") return state;
      if (!canSubmit(acknowledgePinned)) {
        const refused: ProposalState = { phase: "refused", status: 0, error: { code: "submit_blocked", message: state.preview.submit_blockers.join("; ") || "the preview does not allow submit", choices: null, diff: null } };
        setState(refused);
        return refused;
      }
      const proposed = acknowledgePinned ? { ...state.input.proposed, acknowledge_pinned_tests: true } : state.input.proposed;
      setState({ phase: "busy" });
      const next = await postProposal({ workflow_id: workflowId, kind, stage: "submit", reason: state.input.reason, proposed, preview_token: state.preview.preview_token })
        .then(({ status, body }) => classify(status, body, null))
        .catch(failed);
      setState(next);
      return next;
    },
    [workflowId, kind, state, canSubmit],
  );

  const list = useCallback(async (): Promise<ProposalRecord[]> => {
    const { body } = await postProposal({ workflow_id: workflowId, kind, stage: "list" });
    return "stage" in body && body.stage === "list" ? body.items : [];
  }, [workflowId, kind]);

  const reset = useCallback(() => setState(IDLE), []);
  return { state, preview, submit, canSubmit, list, reset };
};
