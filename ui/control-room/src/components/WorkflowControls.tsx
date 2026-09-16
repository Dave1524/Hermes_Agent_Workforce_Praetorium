import { useState } from "react";
import PauseDialog from "@/components/dialogs/PauseDialog";
import ResumeDialog from "@/components/dialogs/ResumeDialog";
import RetireDialog from "@/components/dialogs/RetireDialog";
import RetryDialog from "@/components/dialogs/RetryDialog";
import RunNowDialog from "@/components/dialogs/RunNowDialog";
import ScheduleDialog from "@/components/dialogs/ScheduleDialog";
import StopDialog from "@/components/dialogs/StopDialog";
import { buttonClass } from "@/components/dialogs/DialogFrame";
import type { WorkflowDetail } from "@/model/workflowDetail";
import LastActionPanel from "./LastActionPanel";
import { Panel } from "./Panel";
import ProposalsList from "./ProposalsList";

type Open = "pause" | "resume" | "run_now" | "retry" | "stop" | "schedule" | "retire" | null;

const LABELS: Record<string, string> = { pause: "Pause", resume: "Resume", run_now: "Run now", retry: "Retry", stop: "Stop" };
const isOpenable = (id: string): id is Exclude<Open, null | "schedule" | "retire"> => id in LABELS;

interface Props {
  detail: WorkflowDetail;
  onChanged: () => void;
}

export default function WorkflowControls({ detail, onChanged }: Props) {
  const [open, setOpen] = useState<Open>(null);
  const [menu, setMenu] = useState(false);
  const [proposalsTick, setProposalsTick] = useState(0);
  const { row } = detail;
  const changed = () => {
    onChanged();
    setProposalsTick((t) => t + 1);
  };
  const close = () => setOpen(null);
  const dialogProps = { workflowId: row.id, workflowName: row.name, onClose: close, onChanged: changed };
  const dependencyProps = { requiredBy: row.requiredBy, guards: row.guards };

  return (
    <Panel title="Controls">
      <div data-testid="controls">
        <div className="flex items-center gap-2 flex-wrap">
          {detail.actions.filter((a) => isOpenable(a.id)).map((a) => (
            <button
              key={a.id}
              type="button"
              className={a.id === "stop" ? buttonClass.danger : buttonClass.primary}
              disabled={!a.enabled}
              title={a.enabled ? undefined : (a.reason ?? "not available")}
              onClick={() => isOpenable(a.id) && setOpen(a.id)}
            >
              {LABELS[a.id]}
            </button>
          ))}
          {detail.actions.length === 0 && <span className="text-xs text-muted">No control actions offered for this workflow{detail.controlSource ? ` (control source ${detail.controlSource})` : ""}.</span>}
          <div className="relative ml-auto">
            <button type="button" className={buttonClass.secondary} aria-haspopup="menu" aria-expanded={menu} aria-label="More" onClick={() => setMenu((m) => !m)}>
              ⋯
            </button>
            {menu && (
              <div role="menu" className="absolute right-0 mt-1 bg-surface-2 border border-border rounded shadow-lg z-10 min-w-[11rem] py-1">
                <MenuItem onClick={() => { setMenu(false); setOpen("schedule"); }}>Change schedule…</MenuItem>
                <MenuItem onClick={() => { setMenu(false); setOpen("retire"); }} danger>Retire…</MenuItem>
              </div>
            )}
          </div>
        </div>
        <div className="mt-3 text-xs text-muted">
          Every action goes through the control broker and comes back as a receipt; nothing here is applied optimistically.
        </div>
        <div className="mt-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1.5">Last control action</div>
          <LastActionPanel lastAction={detail.lastAction} />
        </div>
        <div className="mt-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted mb-1.5">Proposals</div>
          <ProposalsList workflowId={row.id} tick={proposalsTick} />
        </div>
      </div>
      {open === "pause" && <PauseDialog {...dialogProps} {...dependencyProps} />}
      {open === "resume" && <ResumeDialog {...dialogProps} />}
      {open === "run_now" && <RunNowDialog {...dialogProps} />}
      {open === "retry" && <RetryDialog {...dialogProps} retryOf={detail.lastRun?.id ?? null} disabledReason={detail.actions.find((a) => a.id === "retry")?.reason ?? null} />}
      {open === "stop" && <StopDialog {...dialogProps} {...dependencyProps} />}
      {open === "schedule" && <ScheduleDialog {...dialogProps} timers={detail.triggers} />}
      {open === "retire" && <RetireDialog {...dialogProps} />}
    </Panel>
  );
}

function MenuItem({ onClick, children, danger = false }: { onClick: () => void; children: React.ReactNode; danger?: boolean }) {
  return (
    <button type="button" role="menuitem" onClick={onClick} className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-surface-3 ${danger ? "text-red" : "text-text-2"}`}>
      {children}
    </button>
  );
}
