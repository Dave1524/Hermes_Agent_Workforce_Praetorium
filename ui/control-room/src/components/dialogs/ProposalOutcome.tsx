import type { ProposalState } from "./useProposal";

export default function ProposalOutcome({ state }: { state: ProposalState }) {
  switch (state.phase) {
    case "idle":
    case "previewed":
      return null;
    case "busy":
      return <p className="text-xs text-muted font-mono" role="status">Working…</p>;
    case "submitted":
      return (
        <div className="bg-green-dim border border-green/30 rounded p-3 text-xs" data-testid="submitted">
          <p className="text-green font-medium">{state.submitted.pr.draft ? "Draft pull request opened." : "Pull request opened."}</p>
          <a href={state.submitted.pr.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline font-mono">
            Pull request #{state.submitted.pr.number ?? "?"}{state.submitted.pr.branch ? ` · ${state.submitted.pr.branch}` : ""}
          </a>
        </div>
      );
    case "refused":
      return (
        <div className="bg-amber-dim border border-amber/30 rounded p-3 text-xs" role="alert" data-testid="refusal">
          <span className="font-mono text-amber font-semibold">{state.error.code}</span>
          {state.error.message && <span className="text-text-2"> · {state.error.message}</span>}
          {state.status > 0 && <span className="text-muted font-mono"> · HTTP {state.status}</span>}
          {state.error.choices && <p className="mt-1 font-mono text-text-2">choices: {state.error.choices.join(", ")}</p>}
          {state.error.diff && <pre className="mt-1 max-h-40 overflow-auto font-mono text-[11px] text-text-2 whitespace-pre">{state.error.diff}</pre>}
        </div>
      );
    case "failed":
      return (
        <div className="bg-red-dim border border-red/30 rounded p-3 text-xs" role="alert" data-testid="failure">
          <span className="font-mono text-red font-semibold">{state.status > 0 ? `HTTP ${state.status}` : "request failed"}</span>
          <span className="text-text-2"> · {state.message}</span>
        </div>
      );
  }
}
