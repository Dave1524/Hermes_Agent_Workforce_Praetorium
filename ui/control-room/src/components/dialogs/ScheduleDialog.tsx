import { useState } from "react";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import ProposalGate from "./ProposalGate";
import ProposalOutcome from "./ProposalOutcome";
import ProposalPreviewView from "./ProposalPreviewView";
import { useProposal } from "./useProposal";

export interface ProposalDialogProps {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
  onChanged: () => void;
}

interface Props extends ProposalDialogProps {
  timers: Array<{ unit: string; kind: string | null }>;
}

const PERSISTENT = [
  ["keep", "keep the unit's value"],
  ["true", "true — fire a missed elapse on boot"],
  ["false", "false — skip missed elapses"],
] as const;

const parsePersistent = (v: string): boolean | null => (v === "true" ? true : v === "false" ? false : null);
const parseLines = (v: string): string[] => v.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

export default function ScheduleDialog({ workflowId, workflowName, timers, onClose, onChanged }: Props) {
  const timerUnits = timers.filter((t) => t.kind === "timer").map((t) => t.unit);
  const [onCalendar, setOnCalendar] = useState("");
  const [delay, setDelay] = useState("");
  const [persistent, setPersistent] = useState<string>("keep");
  const [trigger, setTrigger] = useState<string>(timerUnits[0] ?? "");
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const api = useProposal(workflowId, "schedule");
  const editing = api.state.phase === "idle" || api.state.phase === "refused" || api.state.phase === "failed";
  const previewed = api.state.phase === "previewed";
  const done = api.state.phase === "submitted";
  const canPreview = parseLines(onCalendar).length > 0 && reason.trim() !== "";

  const preview = () =>
    api.preview({
      reason: reason.trim(),
      proposed: {
        on_calendar: parseLines(onCalendar),
        randomized_delay_sec: delay.trim() === "" ? null : delay.trim(),
        persistent: parsePersistent(persistent),
        trigger: timerUnits.length >= 2 ? trigger || null : null,
      },
    });
  const submit = async () => {
    const next = await api.submit(acknowledged);
    if (next.phase === "submitted") onChanged();
  };

  return (
    <DialogFrame
      title={`Change schedule — ${workflowName}`}
      onClose={onClose}
      wide
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {previewed && <button className={buttonClass.secondary} onClick={api.reset}>Edit</button>}
          {!done && !previewed && <button className={buttonClass.primary} onClick={preview} disabled={!canPreview || api.state.phase === "busy"}>Preview</button>}
          {previewed && <button className={buttonClass.primary} onClick={submit} disabled={!api.canSubmit(acknowledged)}>Open pull request</button>}
        </>
      }
    >
      <p>A schedule change is a pull request against the timer unit, never an edit on this box. Preview builds the branch and runs the check bundle; the pull request opens only from a byte-identical preview.</p>
      {(editing || api.state.phase === "busy") && (
        <div className="space-y-3">
          <Field label="OnCalendar (one expression per line)" hint="systemd calendar syntax, e.g. Tue..Sat 03:00 or daily">
            <textarea className={`${inputClass} min-h-[3.5rem] font-mono`} value={onCalendar} onChange={(e) => setOnCalendar(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="RandomizedDelaySec" hint="blank keeps the unit's value">
              <input className={`${inputClass} font-mono`} value={delay} onChange={(e) => setDelay(e.target.value)} placeholder="e.g. 5m" />
            </Field>
            <Field label="Persistent">
              <select className={inputClass} value={persistent} onChange={(e) => setPersistent(e.target.value)}>
                {PERSISTENT.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </Field>
          </div>
          {timerUnits.length >= 2 && (
            <Field label="Trigger" hint="this workflow has several timers; the change applies to one">
              <select className={`${inputClass} font-mono`} value={trigger} onChange={(e) => setTrigger(e.target.value)}>
                {timerUnits.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </Field>
          )}
          <Field label="Reason (required; becomes the pull request body)">
            <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
      )}
      {api.state.phase === "previewed" && <ProposalPreviewView preview={api.state.preview} />}
      <ProposalGate api={api} acknowledged={acknowledged} onAcknowledge={setAcknowledged} />
      <ProposalOutcome state={api.state} />
    </DialogFrame>
  );
}
