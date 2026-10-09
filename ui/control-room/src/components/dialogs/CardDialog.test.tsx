import { render, screen, within } from "@testing-library/react";
import { ACTIVITY, COLUMNS, STATED, cardDetail } from "@/api/boardFixtures.test-helpers";
import type { CardDetail } from "@/api/schemas/board";
import { MOVE_LABELS } from "@/model/card";
import CardDialog from "./CardDialog";

const FIELDS = ["title", "brief", "idea", "research_on", "deadline", "priority", "tags", "scope"];

const open = (column: (typeof COLUMNS)[number], over: Partial<CardDetail> = {}) => {
  const onClose = vi.fn();
  render(<CardDialog card={cardDetail(column, over)} onClose={onClose} />);
  return onClose;
};

describe("CardDialog, read-only", () => {
  describe.each(COLUMNS)("in %s", (column) => {
    it("unlocks exactly the fields the read model states and offers exactly its moves", () => {
      open(column);
      const dialog = screen.getByRole("dialog");
      for (const name of FIELDS) {
        const node = dialog.querySelector(`[data-field="${name}"]`);
        expect(node, name).not.toBeNull();
        expect(node?.getAttribute("data-editable"), name).toBe(String(STATED[column].editable.includes(name)));
      }
      expect(dialog.querySelector('[data-field="owner"]')?.getAttribute("data-editable")).toBe("false");
      const moves = within(dialog).queryAllByRole("button").filter((b) => b.hasAttribute("data-move"));
      expect(moves.map((b) => b.textContent)).toEqual(STATED[column].moves.map((m) => MOVE_LABELS[m]));
      for (const button of moves) expect(button).toBeDisabled();
      expect(screen.getByTestId("card-column")).toHaveTextContent(column);
    });

    it("writes nothing: every text control is read-only and no save is offered", () => {
      open(column);
      for (const area of screen.getAllByRole("textbox")) expect(area).toHaveAttribute("readonly");
      expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /^add$/i })).toBeNull();
      expect(screen.getByText("Moves by decision only")).toBeInTheDocument();
    });
  });

  it("lays out the mockup: title, chips, id, brief provenance, idea, activity newest first, side panel", () => {
    open("Todo", { scheduled: true });
    expect(screen.getByRole("dialog", { name: "Vector search options for the vault" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vector search options for the vault" })).toBeInTheDocument();
    expect(screen.getByTestId("card-scheduled")).toHaveTextContent("Scheduled Tue 6 Oct");
    expect(screen.getByText("vault-vector-search")).toBeInTheDocument();
    expect(screen.getByTestId("brief-provenance")).toHaveTextContent("v2 by A run, approved 28 Sep");
    expect((screen.getByLabelText("Brief") as HTMLTextAreaElement).value).toContain("## Acceptance");
    expect(screen.getByLabelText("Idea")).toHaveValue("Can the vault search run locally instead of over an API?");
    const rows = within(screen.getByTestId("activity")).getAllByRole("listitem");
    expect(rows).toHaveLength(ACTIVITY.length);
    expect(rows[0]).toHaveTextContent("Brief approved by Dave");
    expect(rows[4]).toHaveTextContent("Created by Dave");
    const side = screen.getByRole("complementary", { name: "Card details" });
    expect(side).toHaveTextContent("2026-10-16");
    expect(side).toHaveTextContent("search");
    expect(side).toHaveTextContent("vault:05_knowledge");
    expect(within(side).getByText("Owner").parentElement).toHaveTextContent("claudius");
  });

  it("names a Blocked card's cause", () => {
    open("Blocked", { blockedCause: "returned twice" });
    expect(screen.getByTestId("card-blocked")).toHaveTextContent("Blocked: returned twice");
  });

  it("badges an approved card that waits in In Review for main", () => {
    open("In Review", { approvedLanding: true, moves: [] });
    expect(screen.getByTestId("card-landing")).toHaveTextContent("approved, lands within the hour");
  });

  it("shows a Done card's outcome", () => {
    open("Done", { outcome: "withdrawn" });
    expect(screen.getByTestId("card-outcome")).toHaveTextContent("withdrawn");
  });

  it("shows no research section until a run has published", () => {
    open("Todo");
    expect(screen.queryByTestId("card-research")).toBeNull();
  });

  it("renders the page beside each acceptance answer, its Notion link, and the edited-since mark", () => {
    open("In Review", {
      research: {
        status: "available",
        url: "https://notion.example/p",
        text: "## Findings\nlocal works",
        changed: true,
        acceptance: [
          { line: "each option has a licence", answer: "MET" },
          { line: "one recommendation", answer: "NOT MET" },
          { line: "a test query ran", answer: null },
        ],
      },
    });
    expect(screen.getByRole("link", { name: "Open in Notion" })).toHaveAttribute("href", "https://notion.example/p");
    expect(screen.getByTestId("page-changed")).toBeInTheDocument();
    const lines = within(screen.getByTestId("acceptance")).getAllByRole("listitem");
    expect(lines.map((l) => l.textContent)).toEqual(["METeach option has a licence", "NOT METone recommendation", "no answera test query ran"]);
    expect(screen.getByText(/local works/)).toBeInTheDocument();
  });

  it("says the page could not be read without hiding the card", () => {
    open("In Review", { research: { status: "unavailable", reason: "NOTION_RESEARCH_DS not set", acceptance: [] } });
    expect(screen.getByRole("status")).toHaveTextContent("NOTION_RESEARCH_DS not set");
    expect(screen.getByTestId("card-column")).toHaveTextContent("In Review");
  });

  it("links a run in the activity to its receipt", () => {
    open("In Review", { activity: [{ ts: "2026-10-05T04:30:00Z", kind: "picked", actor: "run:r1", runId: "r1", detail: "research", outcome: "artifact" }] });
    expect(screen.getByRole("link", { name: "receipt" })).toHaveAttribute("href", "/app/runs/r1");
  });

  it("closes from the dismiss button and Escape", () => {
    const onClose = open("Todo");
    screen.getByRole("button", { name: "Dismiss" }).click();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
