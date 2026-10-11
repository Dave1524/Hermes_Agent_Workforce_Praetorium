import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { COLUMNS, STATED, cardDetail } from "@/api/boardFixtures.test-helpers";
import type { CardDetail } from "@/api/schemas/board";
import type { CardWriter, WriteResult } from "@/components/card/cardWriter";
import { MOVE_LABELS } from "@/model/card";
import CardDialog from "./CardDialog";

const OK: WriteResult = { ok: true, card: "vault-vector-search", rev: 6, briefHash: "b".repeat(64) };
const PAGE = { status: "available", url: "https://notion.invalid/p", text: "Findings.", pageHash: "c".repeat(64), publishedHash: "c".repeat(64), changed: false, acceptance: [] };

const makeWriter = (result: WriteResult = OK): CardWriter => ({
  create: vi.fn().mockResolvedValue(OK),
  edit: vi.fn().mockResolvedValue(result),
  brief: vi.fn().mockResolvedValue(result),
  note: vi.fn().mockResolvedValue(result),
  decide: vi.fn().mockResolvedValue(result),
});

const open = (column: (typeof COLUMNS)[number], over: Partial<CardDetail> = {}, writer = makeWriter()) => {
  const onChanged = vi.fn();
  render(<CardDialog card={cardDetail(column, over)} onClose={vi.fn()} writer={writer} onChanged={onChanged} onReload={vi.fn()} />);
  return { writer, onChanged };
};

const move = (name: string) => screen.getByRole("dialog").querySelector(`[data-move="${name}"]`) as HTMLButtonElement;

describe("CardDialog, decisions", () => {
  describe.each(COLUMNS)("in %s", (column) => {
    it("offers exactly the moves the read model states, live", () => {
      open(column, column === "In Review" ? { research: PAGE } : {});
      const buttons = within(screen.getByRole("dialog")).queryAllByRole("button").filter((b) => b.hasAttribute("data-move"));
      expect(buttons.map((b) => b.textContent)).toEqual(STATED[column].moves.map((m) => MOVE_LABELS[m]));
      for (const button of buttons) expect(button).toBeEnabled();
    });
  });

  it("approves a brief by its hash at the rendered revision", async () => {
    const { writer, onChanged } = open("Refine");
    fireEvent.click(move("approve_brief"));
    await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("approve_brief", 5, { brief_hash: "a".repeat(64) }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(null));
  });

  it("unblocks without a reason", async () => {
    const { writer } = open("Blocked");
    fireEvent.click(move("unblock"));
    await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("unblock", 5, {}));
  });

  it.each([
    ["Refine", "return_brief", { brief_hash: "a".repeat(64) }],
    ["Refine", "withdraw", {}],
    ["In Review", "request_changes", {}],
    ["In Review", "reject", {}],
  ] as const)("asks for a reason before %s %s, and sends it", async (column, verb, extra) => {
    const { writer } = open(column, column === "In Review" ? { research: PAGE } : {});
    fireEvent.click(move(verb));
    expect(writer.decide).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: `Confirm ${MOVE_LABELS[verb].toLowerCase()}` });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "keep it local" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(writer.decide).toHaveBeenCalledWith(verb, 5, { ...extra, reason: "keep it local" }));
  });

  it("lets a reason be cancelled, sending nothing", () => {
    const { writer } = open("Refine");
    fireEvent.click(move("withdraw"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Reason")).toBeNull();
    expect(writer.decide).not.toHaveBeenCalled();
  });

  it("blocks with an optional reason", async () => {
    const { writer } = open("Todo");
    fireEvent.click(move("block"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
    await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("block", 5, {}));
  });

  it("approves the page the popup rendered, by its hash", async () => {
    const { writer } = open("In Review", { research: PAGE });
    fireEvent.click(move("approve"));
    await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("approve", 5, { page_hash: PAGE.pageHash }));
  });

  it("cannot approve a page it has not read", () => {
    open("In Review", { research: { status: "unavailable", reason: "no token", acceptance: [] } });
    expect(move("approve")).toBeDisabled();
    expect(move("approve").title).toMatch(/page/i);
    expect(move("reject")).toBeEnabled();
  });

  it("cannot approve or return a brief that is not the current one", () => {
    open("Refine", { brief: { ...cardDetail("Refine").brief!, current: false } });
    expect(move("approve_brief")).toBeDisabled();
    expect(move("return_brief")).toBeDisabled();
    expect(move("withdraw")).toBeEnabled();
  });

  it("will not approve a brief over unsaved edits to it", () => {
    open("Refine");
    fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "## Do\nsomething else\n" } });
    expect(move("approve_brief")).toBeDisabled();
  });

  it("shows a stale refusal and offers a reload, changing nothing", async () => {
    const onReload = vi.fn();
    const writer = makeWriter({ ok: false, stale: true, message: "stale: the page changed" });
    render(<CardDialog card={cardDetail("In Review", { research: PAGE })} onClose={vi.fn()} writer={writer} onReload={onReload} />);
    fireEvent.click(move("approve"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed while you were editing/i);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(onReload).toHaveBeenCalled();
  });

  it("shows the broker's refusal as it is", async () => {
    open("Todo", {}, makeWriter({ ok: false, stale: false, message: "broker_unavailable: no socket" }));
    fireEvent.click(move("block"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("broker_unavailable: no socket");
  });

  describe("Save and approve", () => {
    it("saves the changed brief, then approves the hash the save returned at the new revision", async () => {
      const { writer, onChanged } = open("Refine");
      const both = screen.getByRole("button", { name: "Save and approve" });
      expect(both).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "## Do\nnew\n" } });
      fireEvent.click(both);
      await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("approve_brief", 6, { brief_hash: "b".repeat(64) }));
      expect(writer.brief).toHaveBeenCalledWith(5, "## Do\nnew\n");
      await waitFor(() => expect(onChanged).toHaveBeenCalled());
    });

    it("keeps the saved brief and says so when the approval is refused", async () => {
      const writer = makeWriter();
      (writer.decide as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: false, stale: false, message: "broker_unavailable: no socket" });
      open("Refine", {}, writer);
      fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "## Do\nnew\n" } });
      fireEvent.click(screen.getByRole("button", { name: "Save and approve" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/brief was saved.*broker_unavailable/i);
      expect(screen.getByRole("button", { name: "Save brief" })).toBeDisabled();
    });

    it("is only offered where approving a brief is a move", () => {
      open("Todo");
      expect(screen.queryByRole("button", { name: "Save and approve" })).toBeNull();
    });
  });

  describe("Save and unblock", () => {
    it("saves the new date, then unblocks at the new revision", async () => {
      const { writer } = open("Blocked");
      const both = screen.getByRole("button", { name: "Save and unblock" });
      expect(both).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Deadline"), { target: { value: "2026-12-01" } });
      fireEvent.click(both);
      await waitFor(() => expect(writer.edit).toHaveBeenCalledWith(5, { deadline: "2026-12-01" }));
      await waitFor(() => expect(writer.decide).toHaveBeenCalledWith("unblock", 6, {}));
    });

    it("is only offered on a card that can be unblocked", () => {
      open("Todo");
      expect(screen.queryByRole("button", { name: "Save and unblock" })).toBeNull();
    });
  });
});
