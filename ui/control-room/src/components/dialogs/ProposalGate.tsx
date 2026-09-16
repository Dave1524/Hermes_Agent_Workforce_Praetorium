import { pinnedOnlyBlockers, type ProposalApi } from "./useProposal";

interface Props {
  api: ProposalApi;
  acknowledged: boolean;
  onAcknowledge: (v: boolean) => void;
}

export default function ProposalGate({ api, acknowledged, onAcknowledge }: Props) {
  if (api.state.phase !== "previewed") return null;
  const preview = api.state.preview;
  const pinnedFailed = preview.checks.some((c) => c.class === "pinned" && c.status === "fail");
  return (
    <div className="space-y-2 text-xs">
      {pinnedOnlyBlockers(preview) && (
        <label className="flex items-start gap-2 text-text-2">
          <input type="checkbox" checked={acknowledged} onChange={(e) => onAcknowledge(e.target.checked)} className="accent-accent mt-0.5" />
          <span>Acknowledge the pinned test failures and open the pull request anyway.</span>
        </label>
      )}
      {pinnedFailed && <p className="text-muted">A pinned suite fails, so the pull request opens as a draft.</p>}
    </div>
  );
}
