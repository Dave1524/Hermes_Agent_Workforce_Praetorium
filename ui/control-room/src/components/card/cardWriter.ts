import { ApiError, postBoard } from "@/api/client";
import type { BoardWriteRequest } from "@/api/schemas/boardWrite";

export type WriteResult = { ok: true; card: string | null; rev: number | null } | { ok: false; stale: boolean; message: string };

export interface CardWriter {
  create: (fields: Record<string, unknown>) => Promise<WriteResult>;
  edit: (rev: number, fields: Record<string, unknown>) => Promise<WriteResult>;
  brief: (rev: number, text: string) => Promise<WriteResult>;
  note: (text: string) => Promise<WriteResult>;
}

const send = async (request: BoardWriteRequest): Promise<WriteResult> => {
  try {
    const { status, body } = await postBoard(request);
    if (body.ok) return { ok: true, card: body.card ?? null, rev: body.view?.rev ?? null };
    return { ok: false, stale: status === 409, message: body.error ?? `HTTP ${status}` };
  } catch (e) {
    return { ok: false, stale: false, message: e instanceof ApiError || e instanceof Error ? e.message : String(e) };
  }
};

export const cardWriter = (card: string): CardWriter => ({
  create: (fields) => send({ verb: "create", ...fields }),
  edit: (rev, fields) => send({ verb: "edit", card, expect_rev: rev, fields }),
  brief: (rev, text) => send({ verb: "brief", card, expect_rev: rev, text }),
  note: (text) => send({ verb: "note", card, text }),
});
