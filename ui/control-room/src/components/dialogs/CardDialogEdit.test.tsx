import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { COLUMNS, STATED, cardDetail } from "@/api/boardFixtures.test-helpers";
import type { CardDetail } from "@/api/schemas/board";
import type { CardWriter, WriteResult } from "@/components/card/cardWriter";
import { emptyCard } from "@/model/cardDraft";
import CardDialog from "./CardDialog";

const OK: WriteResult = { ok: true, card: "vault-vector-search", rev: 6 };

const makeWriter = (result: WriteResult = OK): CardWriter => ({
  create: vi.fn().mockResolvedValue({ ok: true, card: "new-card", rev: 1 }),
  edit: vi.fn().mockResolvedValue(result),
  brief: vi.fn().mockResolvedValue(result),
  note: vi.fn().mockResolvedValue(result),
});

const open = (card: CardDetail, writer = makeWriter()) => {
  const onClose = vi.fn();
  const onChanged = vi.fn();
  const onReload = vi.fn();
  render(<CardDialog card={card} onClose={onClose} writer={writer} onChanged={onChanged} onReload={onReload} />);
  return { writer, onClose, onChanged, onReload };
};

const NAMED: Record<string, string> = { title: "Title", idea: "Idea", brief: "Brief", research_on: "Research date", deadline: "Deadline", priority: "Priority", tags: "Tags", scope: "Scope" };

describe("CardDialog, edit mode", () => {
  afterEach(() => vi.restoreAllMocks());

  describe.each(COLUMNS)("in %s", (column) => {
    it("makes exactly the stated fields editable and gives the rest a reason", () => {
      open(cardDetail(column));
      const dialog = screen.getByRole("dialog");
      for (const [name, label] of Object.entries(NAMED)) {
        const stated = STATED[column].editable.includes(name);
        const control = within(dialog).queryByLabelText(label) as HTMLInputElement | null;
        if (stated) {
          expect(control, name).not.toBeNull();
          expect(control, name).not.toHaveAttribute("readonly");
        } else {
          expect(control === null || control.hasAttribute("readonly") || control.hasAttribute("disabled"), name).toBe(true);
          expect(dialog.querySelector(`[data-lock="${name}"]`)?.textContent, name).toMatch(/Locked/);
        }
      }
      expect(within(dialog).queryByLabelText("Add a note")).not.toBeNull();
    });
  });

  it("locks the idea and scope after the first research run, with the reason", () => {
    open(cardDetail("Todo", { editable: ["title", "brief", "priority", "tags", "notes"], runs: [{ runId: "r1", purpose: "research", void: false }] }));
    expect(screen.getByRole("dialog").querySelector('[data-lock="idea"]')?.textContent).toMatch(/after the first research run/);
  });

  it("enables Save on the brief only once the text has changed, and saves it at the rendered revision", async () => {
    const { writer, onChanged } = open(cardDetail("Refine"));
    const save = screen.getByRole("button", { name: "Save brief" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "## Do\nsomething new\n" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(writer.brief).toHaveBeenCalledWith(5, "## Do\nsomething new\n"));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(null));
  });

  it("carries the new revision into the next save, so two saves in one session do not collide", async () => {
    const { writer } = open(cardDetail("Todo"));
    fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "## Do\nnew\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save brief" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save brief" })).toBeDisabled());
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(writer.edit).toHaveBeenCalledWith(6, { priority: "low" }));
  });

  it("saves only the changed details, a cleared date as null, at the rendered revision", async () => {
    const { writer } = open(cardDetail("Todo"));
    const save = screen.getByRole("button", { name: "Save details" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.change(screen.getByLabelText("Deadline"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Tags"), { target: { value: "search, local" } });
    fireEvent.click(save);
    await waitFor(() => expect(writer.edit).toHaveBeenCalledWith(5, { priority: "low", deadline: null, tags: ["search", "local"] }));
  });

  it("adds a note, clears the box, and offers Add only with text", async () => {
    const { writer, onChanged } = open(cardDetail("In Progress"));
    const add = screen.getByRole("button", { name: "Add" });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Add a note"), { target: { value: "keep it local" } });
    fireEvent.click(add);
    await waitFor(() => expect(writer.note).toHaveBeenCalledWith("keep it local"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("says a stale save was refused and reloads on request", async () => {
    const { onReload } = open(cardDetail("Todo"), makeWriter({ ok: false, stale: true, message: "stale: card is at revision 6, you saved 5" }));
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed while you were editing/i);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(onReload).toHaveBeenCalled();
  });

  it("shows any other refusal as written", async () => {
    open(cardDetail("Todo"), makeWriter({ ok: false, stale: false, message: "research date 2026-11-01 is after the deadline 2026-10-16" }));
    fireEvent.change(screen.getByLabelText("Research date"), { target: { value: "2026-11-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("is after the deadline");
  });

  describe("the unsaved-edit guard", () => {
    const attempts: Array<[string, () => void]> = [
      ["the dismiss button", () => fireEvent.click(screen.getByRole("button", { name: "Dismiss" }))],
      ["Escape", () => fireEvent.keyDown(window, { key: "Escape" })],
      ["a click outside", () => fireEvent.click(screen.getByRole("dialog").parentElement as HTMLElement)],
    ];

    it.each(attempts)("asks before %s discards an edit, and stays open on a no", (_name, attempt) => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const { onClose } = open(cardDetail("Todo"));
      fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Changed title" } });
      attempt();
      expect(confirm).toHaveBeenCalledTimes(1);
      expect(onClose).not.toHaveBeenCalled();
    });

    it.each(attempts)("closes after %s once the discard is confirmed", (_name, attempt) => {
      vi.spyOn(window, "confirm").mockReturnValue(true);
      const { onClose } = open(cardDetail("Todo"));
      fireEvent.change(screen.getByLabelText("Add a note"), { target: { value: "half a thought" } });
      attempt();
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes without asking when nothing changed", () => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const { onClose } = open(cardDetail("Todo"));
      fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      expect(confirm).not.toHaveBeenCalled();
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("treats an edit back to the original value as clean", () => {
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      const { onClose } = open(cardDetail("Todo"));
      fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "low" } });
      fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
      fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      expect(confirm).not.toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("creating a card in the same popup, empty", () => {
    it("offers Create only with a title, an idea and a scope, then sends them with the brief", async () => {
      const { writer, onChanged } = open(emptyCard());
      const create = screen.getByRole("button", { name: "Create card" });
      expect(create).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Alpha question" } });
      fireEvent.change(screen.getByLabelText("Idea"), { target: { value: "Does it hold?" } });
      expect(create).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Scope"), { target: { value: "vault:05_knowledge" } });
      fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "# Question\nq\n" } });
      fireEvent.click(create);
      await waitFor(() =>
        expect(writer.create).toHaveBeenCalledWith({
          title: "Alpha question",
          idea: "Does it hold?",
          scope: ["vault:05_knowledge"],
          priority: "normal",
          tags: [],
          owner: "claudius",
          kind: "research",
          brief: "# Question\nq\n",
        }),
      );
      await waitFor(() => expect(onChanged).toHaveBeenCalledWith("new-card"));
    });

    it("has no note box and no moves", () => {
      open(emptyCard());
      expect(screen.queryByLabelText("Add a note")).toBeNull();
      expect(screen.queryByText("Moves by decision only")).toBeNull();
    });
  });
});
