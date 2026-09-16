import ReceiptPanel from "@/components/ReceiptPanel";
import type { ControlState } from "./useControlAction";

const HTTP_NOTE: Record<number, string> = {
  400: "the request was refused",
  403: "the broker denied this caller or the workflow is not allowlisted",
  404: "the workflow is unknown to the API",
  500: "the broker's command failed",
  501: "the control broker is not wired on this box",
  502: "the control broker is unreachable",
  503: "the API is degraded",
  504: "the control broker timed out",
};

export default function ControlOutcome({ state }: { state: ControlState }) {
  switch (state.phase) {
    case "idle":
      return null;
    case "busy":
      return <p className="text-xs text-muted font-mono" role="status">Working…</p>;
    case "previewed":
    case "applied":
      return state.response.receipt ? <ReceiptPanel receipt={state.response.receipt} /> : null;
    case "refused":
      return (
        <div className="bg-amber-dim border border-amber/30 rounded p-3 text-xs" role="alert" data-testid="refusal">
          <span className="font-mono text-amber font-semibold">{state.refusal.code}</span>
          {state.refusal.message && <span className="text-text-2"> · {state.refusal.message}</span>}
          {state.status > 0 && <span className="text-muted font-mono"> · HTTP {state.status}</span>}
          {state.response?.receipt && <div className="mt-2"><ReceiptPanel receipt={state.response.receipt} /></div>}
        </div>
      );
    case "failed":
      return (
        <div className="bg-red-dim border border-red/30 rounded p-3 text-xs" role="alert" data-testid="failure">
          <span className="font-mono text-red font-semibold">{state.status > 0 ? `HTTP ${state.status}` : "request failed"}</span>
          <span className="text-text-2"> · {HTTP_NOTE[state.status] ?? state.message}</span>
          {HTTP_NOTE[state.status] && <div className="text-muted font-mono mt-1">{state.message}</div>}
          {state.response?.receipt && <div className="mt-2"><ReceiptPanel receipt={state.response.receipt} /></div>}
        </div>
      );
  }
}
