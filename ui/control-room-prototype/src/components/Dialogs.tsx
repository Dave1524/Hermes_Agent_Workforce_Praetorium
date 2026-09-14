import { useState } from "react";
import type { Workflow } from "../data";

interface Props {
  workflow: Workflow;
  dialog: "pause" | "resume" | "run" | "retry" | "stop" | "schedule" | "retire" | null;
  onClose: () => void;
  onConfirm?: (dialog: string, data?: Record<string, string>) => void;
}

export default function Dialogs({ workflow, dialog, onClose, onConfirm }: Props) {
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);

  if (!dialog) return null;

  const handle = (data?: Record<string, string>) => {
    setConfirming(true);
    setTimeout(() => {
      setConfirming(false);
      onConfirm?.(dialog, data);
      onClose();
    }, 800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-bg/80 backdrop-blur-sm" />
      <div
        className="relative bg-surface-2 border border-border-2 rounded-lg shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {dialog === "pause" && (
          <PauseDialog workflow={workflow} onCancel={onClose} onConfirm={() => handle()} confirming={confirming} />
        )}
        {dialog === "resume" && (
          <ResumeDialog workflow={workflow} onCancel={onClose} onConfirm={() => handle()} confirming={confirming} />
        )}
        {dialog === "run" && (
          <RunNowDialog workflow={workflow} onCancel={onClose} onConfirm={() => handle()} confirming={confirming} />
        )}
        {dialog === "retry" && (
          <RetryDialog workflow={workflow} onCancel={onClose} onConfirm={() => handle()} confirming={confirming} />
        )}
        {dialog === "stop" && (
          <StopDialog workflow={workflow} reason={reason} setReason={setReason} onCancel={onClose} onConfirm={() => handle({ reason })} confirming={confirming} />
        )}
        {dialog === "schedule" && (
          <ScheduleDialog workflow={workflow} onCancel={onClose} onConfirm={() => handle()} confirming={confirming} />
        )}
        {dialog === "retire" && (
          <RetireDialog workflow={workflow} reason={reason} setReason={setReason} onCancel={onClose} onConfirm={() => handle({ reason })} confirming={confirming} />
        )}
      </div>
    </div>
  );
}

function DialogHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="p-5 border-b border-border">
      <h2 className="text-text font-semibold text-base">{title}</h2>
      {sub && <p className="text-text-2 text-sm mt-1">{sub}</p>}
    </div>
  );
}

function DialogActions({ onCancel, onConfirm, confirmLabel, destructive, confirming, disabled }: {
  onCancel: () => void; onConfirm: () => void; confirmLabel: string;
  destructive?: boolean; confirming?: boolean; disabled?: boolean;
}) {
  return (
    <div className="p-5 pt-0 flex justify-end gap-2 mt-5">
      <button onClick={onCancel} className="px-3 py-1.5 text-sm text-text-2 border border-border rounded hover:bg-surface-3 transition-colors">
        Cancel
      </button>
      <button
        onClick={onConfirm}
        disabled={disabled || confirming}
        className={`px-3 py-1.5 text-sm rounded font-medium transition-colors disabled:opacity-50 ${
          destructive
            ? "bg-red text-white hover:bg-red/90"
            : "bg-accent text-bg hover:bg-accent-2"
        }`}
      >
        {confirming ? "Working…" : confirmLabel}
      </button>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1.5 text-sm border-b border-border last:border-0">
      <span className="text-text-2">{label}</span>
      <span className="text-text font-mono text-xs pt-0.5">{value}</span>
    </div>
  );
}

function Notice({ children, variant = "info" }: { children: React.ReactNode; variant?: "info" | "warn" }) {
  return (
    <div className={`rounded p-3 text-sm mt-4 ${variant === "warn" ? "bg-amber-dim text-amber border border-amber/20" : "bg-blue-dim text-blue border border-blue/20"}`}>
      {children}
    </div>
  );
}

function PauseDialog({ workflow, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Pause "${workflow.name}"`} sub="Future scheduled runs will be suspended." />
      <div className="p-5">
        <Row label="Workflow" value={workflow.name} />
        <Row label="Agent" value={workflow.agent} />
        <Row label="Schedule" value={workflow.schedule} />
        <Notice variant="info">The current run, if active, will be allowed to finish before pausing takes effect.</Notice>
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Pause workflow" confirming={confirming} />
    </>
  );
}

function ResumeDialog({ workflow, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Resume "${workflow.name}"`} />
      <div className="p-5">
        <Row label="Next scheduled run" value={workflow.schedule} />
        <Row label="Agent" value={workflow.agent} />
        <Notice variant="warn">
          If runs were missed while paused, systemd may immediately start a catch-up run after resuming. Check the schedule to confirm.
        </Notice>
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Resume workflow" confirming={confirming} />
    </>
  );
}

function RunNowDialog({ workflow, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Run "${workflow.name}" now`} sub="This will trigger an immediate out-of-schedule run." />
      <div className="p-5">
        <Row label="Workflow" value={workflow.name} />
        <Row label="Agent" value={workflow.agent} />
        <Row label="Expected output" value={workflow.artifact} />
        <Row label="Est. effect" value="Single run · not counted as catch-up" />
        <Notice>A run ID will be returned on confirmation. Monitor progress in Activity.</Notice>
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Run now" confirming={confirming} />
    </>
  );
}

function RetryDialog({ workflow, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Retry "${workflow.name}"`} />
      <div className="p-5">
        {!workflow.retryEnabled ? (
          <div className="bg-surface-3 border border-border rounded p-3 text-sm text-text-2">
            <p className="font-medium text-text mb-1">Retry unavailable</p>
            <p>This workflow's contract does not declare retry as safe. Retrying could produce duplicate artifacts or duplicate Notion pages.</p>
            <p className="mt-2">To proceed, contact the workflow owner or manually reset the run state before retrying.</p>
          </div>
        ) : (
          <>
            <Row label="Workflow" value={workflow.name} />
            <Row label="Last run" value={workflow.lastRunTimestamp} />
            <Notice>This workflow is declared retry-safe. A new run will be created with the same inputs as the last run.</Notice>
          </>
        )}
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Retry" confirming={confirming} disabled={!workflow.retryEnabled} />
    </>
  );
}

function StopDialog({ workflow, reason, setReason, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Stop "${workflow.name}"`} sub="This will immediately terminate the active run." />
      <div className="p-5">
        <Row label="Run in progress" value="run-aws-20260910-1500" />
        <div className="bg-red-dim border border-red/20 rounded p-3 text-sm text-red mt-4 mb-4">
          Stopping a run mid-execution may leave partial artifacts in Notion or partially-updated system state. Any uncommitted writes may be lost.
        </div>
        <label className="block text-sm text-text-2 mb-1.5">Reason <span className="text-red">*</span></label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Describe why you are stopping this run…"
          className="w-full bg-surface border border-border rounded p-2.5 text-sm text-text resize-none focus:outline-none focus:border-red/60"
        />
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Stop run" destructive confirming={confirming} disabled={!reason.trim()} />
    </>
  );
}

function ScheduleDialog({ workflow, onCancel, onConfirm, confirming }: any) {
  const [proposed, setProposed] = useState("Daily 08:00 Europe/London");
  return (
    <>
      <DialogHeader title="Change schedule" sub="This creates a reviewed PR — the change does not apply immediately." />
      <div className="p-5">
        <Row label="Current schedule" value={workflow.schedule} />
        <Row label="Timezone" value="Europe/London" />
        <Row label="Catch-up enabled" value="No" />
        <div className="mt-4">
          <label className="block text-sm text-text-2 mb-1.5">Proposed schedule</label>
          <input
            value={proposed}
            onChange={(e) => setProposed(e.target.value)}
            className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-text focus:outline-none focus:border-accent/60 font-mono"
          />
        </div>
        <Notice>Changes to systemd timer schedules are version-controlled. A PR will be created for your review before any change is applied.</Notice>
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Create reviewed PR" confirming={confirming} />
    </>
  );
}

function RetireDialog({ workflow, reason, setReason, onCancel, onConfirm, confirming }: any) {
  return (
    <>
      <DialogHeader title={`Retire "${workflow.name}"`} sub="Retirement is irreversible and version-controlled — not an immediate toggle." />
      <div className="p-5">
        <div className="text-sm text-text-2 space-y-1 mb-4">
          <p className="font-medium text-text mb-2">Affected components</p>
          <Row label="Schedules" value="1 cron timer" />
          <Row label="Runners" value={`${workflow.agent} agent`} />
          <Row label="Contracts" value="1 output contract" />
          <Row label="Routes" value="Notion integration route" />
        </div>
        <label className="block text-sm text-text-2 mb-1.5">Reason <span className="text-red">*</span></label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="Why is this workflow being retired?…"
          className="w-full bg-surface border border-border rounded p-2.5 text-sm text-text resize-none focus:outline-none focus:border-accent/60"
        />
        <Notice variant="warn">A PR will be created for Dave to review before any system changes take effect.</Notice>
      </div>
      <DialogActions onCancel={onCancel} onConfirm={onConfirm} confirmLabel="Create retirement PR" confirming={confirming} disabled={!reason.trim()} />
    </>
  );
}
