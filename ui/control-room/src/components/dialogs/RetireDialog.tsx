import { useState } from "react";
import DialogFrame, { Field, buttonClass, inputClass } from "./DialogFrame";
import ProposalGate from "./ProposalGate";
import ProposalOutcome from "./ProposalOutcome";
import ProposalPreviewView from "./ProposalPreviewView";
import type { ProposalDialogProps } from "./ScheduleDialog";
import { useProposal } from "./useProposal";

const RETENTION = ["keep", "archive", "delete"] as const;
const RECEIPT_RETENTION = ["keep", "archive"] as const;

export default function RetireDialog({ workflowId, workflowName, onClose, onChanged }: ProposalDialogProps) {
  const [receipts, setReceipts] = useState<string>("keep");
  const [notion, setNotion] = useState<string>("keep");
  const [inbox, setInbox] = useState<string>("keep");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const api = useProposal(workflowId, "retire");
  const editing = api.state.phase === "idle" || api.state.phase === "refused" || api.state.phase === "failed";
  const previewed = api.state.phase === "previewed";
  const done = api.state.phase === "submitted";
  const canPreview = note.trim() !== "" && reason.trim() !== "";

  const preview = () =>
    api.preview({
      reason: reason.trim(),
      proposed: { artifact_retention: { receipts, notion, inbox, note: note.trim() }, acknowledge_pinned_tests: false },
    });
  const submit = async () => {
    const next = await api.submit(acknowledged);
    if (next.phase === "submitted") onChanged();
  };

  return (
    <DialogFrame
      title={`Retire — ${workflowName}`}
      onClose={onClose}
      wide
      tone="danger"
      footer={
        <>
          <button className={buttonClass.secondary} onClick={onClose}>{done ? "Close" : "Cancel"}</button>
          {previewed && <button className={buttonClass.secondary} onClick={api.reset}>Edit</button>}
          {!done && !previewed && <button className={buttonClass.primary} onClick={preview} disabled={!canPreview || api.state.phase === "busy"}>Preview</button>}
          {previewed && <button className={buttonClass.danger} onClick={submit} disabled={!api.canSubmit(acknowledged)}>Open pull request</button>}
        </>
      }
    >
      <p>Retirement is a pull request that removes the manifest row, unit and contract and records the entry in <span className="font-mono">design/retired-workflows.toml</span>. The retirement gate stays red after the merge until the live residue is cleared by hand.</p>
      {(editing || api.state.phase === "busy") && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <RetentionSelect label="Receipts" value={receipts} onChange={setReceipts} options={RECEIPT_RETENTION} />
            <RetentionSelect label="Notion rows" value={notion} onChange={setNotion} options={RETENTION} />
            <RetentionSelect label="Inbox proposals" value={inbox} onChange={setInbox} options={RETENTION} />
          </div>
          <Field label="Retention note (required)" hint="what stays where, for the record">
            <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Field label="Reason (required; becomes the pull request body)">
            <textarea className={`${inputClass} min-h-[3.5rem]`} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
      )}
      {api.state.phase === "previewed" && <ProposalPreviewView preview={api.state.preview} />}
      <ProposalGate api={api} acknowledged={acknowledged} onAcknowledge={setAcknowledged} />
      <ProposalOutcome state={api.state} />
    </DialogFrame>
  );
}

function RetentionSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: readonly string[] }) {
  return (
    <Field label={label}>
      <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </Field>
  );
}
