import { useState } from "react";
import type { CardDetail } from "@/api/schemas/board";
import type { DecisionVerb } from "@/api/schemas/boardWrite";
import type { CardWriter } from "./cardWriter";
import type { EditProblem } from "./useCardEdit";

const REASONED = new Set<string>(["return_brief", "request_changes", "reject", "withdraw"]);
const ASKS = new Set<string>([...REASONED, "block"]);

export interface CardDecision {
  pending: string | null;
  reason: string;
  busy: boolean;
  problem: EditProblem | null;
  needsReason: boolean;
  unavailable: (move: string) => string | null;
  choose: (move: string) => void;
  setReason: (reason: string) => void;
  confirm: () => void;
  cancel: () => void;
}

interface Editing {
  rev: number;
  busy: boolean;
  briefDirty: boolean;
}

const fieldsFor = (card: CardDetail, move: string): Record<string, unknown> => {
  if (move === "approve_brief" || move === "return_brief") return { brief_hash: card.brief?.hash };
  if (move === "approve") return { page_hash: card.research.pageHash };
  return {};
};

export const useCardDecision = (card: CardDetail, writer: CardWriter, edit: Editing, onChanged: (created: string | null) => void): CardDecision => {
  const [pending, setPending] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<EditProblem | null>(null);

  const unavailable = (move: string): string | null => {
    if (busy || edit.busy) return "Working";
    if ((move === "approve_brief" || move === "return_brief") && !card.brief?.current) return "This brief is not the current one";
    if (move === "approve_brief" && edit.briefDirty) return "Save the brief first, or use Save and approve";
    if (move === "approve" && (card.research.status !== "available" || !card.research.pageHash)) return "The page has not been read; reload the card";
    return null;
  };

  const send = async (move: string, text: string) => {
    setBusy(true);
    setProblem(null);
    const extra = text.trim() ? { reason: text.trim() } : {};
    const result = await writer.decide(move as DecisionVerb, edit.rev, { ...fieldsFor(card, move), ...extra });
    setBusy(false);
    if (!result.ok) return setProblem({ message: result.message, stale: result.stale });
    setPending(null);
    setReason("");
    onChanged(null);
  };

  const choose = (move: string) => {
    if (ASKS.has(move)) return setPending(move);
    void send(move, "");
  };
  const needsReason = pending !== null && REASONED.has(pending);
  const confirm = () => pending && void send(pending, reason);
  const cancel = () => {
    setPending(null);
    setReason("");
  };
  return { pending, reason, busy, problem, needsReason, unavailable, choose, setReason, confirm, cancel };
};
