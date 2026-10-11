import { useState } from "react";
import type { CardDetail } from "@/api/schemas/board";
import type { DecisionVerb } from "@/api/schemas/boardWrite";
import { moveLabel } from "@/model/card";
import { type Draft, type Editing, briefChanged, changesOf, draftOf, isDirty, listOf } from "@/model/cardDraft";
import type { CardWriter, WriteResult } from "./cardWriter";

export interface EditProblem {
  message: string;
  stale: boolean;
}

export interface CardEdit {
  editing: Editing;
  creating: boolean;
  dirty: boolean;
  briefDirty: boolean;
  rev: number;
  busy: boolean;
  problem: EditProblem | null;
  canSaveBrief: boolean;
  canSaveDetails: boolean;
  canAddNote: boolean;
  canCreate: boolean;
  canSaveAndApprove: boolean;
  canSaveAndUnblock: boolean;
  saveBriefAndApprove: () => void;
  saveDetailsAndUnblock: () => void;
  saveBrief: () => void;
  saveDetails: () => void;
  addNote: () => void;
  create: () => void;
}

const DETAIL_KEYS: Array<keyof Draft> = ["title", "idea", "scope", "priority", "tags", "research_on", "deadline"];

export const useCardEdit = (card: CardDetail, writer: CardWriter, onChanged: (created: string | null) => void): CardEdit => {
  const creating = card.id === "";
  const [base, setBase] = useState(() => draftOf(card));
  const [rev, setRev] = useState(card.rev);
  const [draft, setDraft] = useState(base);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<EditProblem | null>(null);
  const changes = changesOf(base, draft, card.editable);
  const dirty = isDirty(base, draft, card.editable);

  const run = async (call: () => Promise<WriteResult>, saved: (result: WriteResult & { ok: true }) => void) => {
    setBusy(true);
    setProblem(null);
    const result = await call();
    setBusy(false);
    if (!result.ok) return setProblem({ message: result.message, stale: result.stale });
    if (result.rev !== null) setRev(result.rev);
    saved(result);
    onChanged(creating ? result.card : null);
  };

  const rebase = (patch: Partial<Draft>) => setBase((b) => ({ ...b, ...patch }));
  const saveDetails = () =>
    void run(() => writer.edit(rev, changes), () => rebase(Object.fromEntries(DETAIL_KEYS.filter((k) => k in changes).map((k) => [k, draft[k]]))));
  const saveBrief = () => void run(() => writer.brief(rev, draft.brief), () => rebase({ brief: draft.brief }));
  const saveThen = (what: string, save: () => Promise<WriteResult>, verb: DecisionVerb, hashed: boolean, saved: () => void) =>
    void run(async () => {
      const first = await save();
      if (!first.ok || first.rev === null) return first;
      saved();
      setRev(first.rev);
      const hash = first.briefHash;
      const decided = hashed && !hash ? null : await writer.decide(verb, first.rev, hashed ? { brief_hash: hash } : {});
      if (decided?.ok) return decided;
      const why = decided ? decided.message : "the server returned no hash";
      return { ok: false as const, stale: decided ? !decided.ok && decided.stale : false, message: `The ${what} was saved, but ${moveLabel(verb).toLowerCase()} failed: ${why}` };
    }, () => undefined);
  const saveBriefAndApprove = () => saveThen("brief", () => writer.brief(rev, draft.brief), "approve_brief", true, () => rebase({ brief: draft.brief }));
  const saveDetailsAndUnblock = () =>
    saveThen("details", () => writer.edit(rev, changes), "unblock", false, () => rebase(Object.fromEntries(DETAIL_KEYS.filter((k) => k in changes).map((k) => [k, draft[k]]))));
  const addNote = () =>
    void run(() => writer.note(draft.note.trim()), () => {
      setDraft((d) => ({ ...d, note: "" }));
    });
  const create = () =>
    void run(
      () =>
        writer.create({
          title: draft.title.trim(),
          idea: draft.idea.trim(),
          scope: listOf(draft.scope),
          priority: draft.priority,
          tags: listOf(draft.tags),
          owner: card.owner,
          kind: card.kind,
          ...(draft.research_on.trim() ? { research_on: draft.research_on.trim() } : {}),
          ...(draft.deadline.trim() ? { deadline: draft.deadline.trim() } : {}),
          ...(draft.brief.trim() ? { brief: draft.brief } : {}),
        }),
      () => undefined,
    );

  return {
    editing: { draft, set: (name, value) => setDraft((d) => ({ ...d, [name]: value })) },
    creating,
    dirty,
    briefDirty: briefChanged(base, draft),
    rev,
    busy,
    problem,
    canSaveBrief: !busy && !creating && briefChanged(base, draft),
    canSaveDetails: !busy && !creating && Object.keys(changes).length > 0,
    canAddNote: !busy && !creating && draft.note.trim() !== "",
    canCreate: !busy && creating && [draft.title, draft.idea, draft.scope].every((v) => v.trim() !== "") && listOf(draft.scope).length > 0,
    canSaveAndApprove: !busy && !creating && briefChanged(base, draft) && card.moves.includes("approve_brief"),
    canSaveAndUnblock: !busy && !creating && Object.keys(changes).length > 0 && card.moves.includes("unblock"),
    saveBriefAndApprove,
    saveDetailsAndUnblock,
    saveBrief,
    saveDetails,
    addNote,
    create,
  };
};
