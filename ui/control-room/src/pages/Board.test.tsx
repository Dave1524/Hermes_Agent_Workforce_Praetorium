import { act, screen, waitFor, within } from "@testing-library/react";
import { COLUMNS, boardOf, cardDetail } from "@/api/boardFixtures.test-helpers";
import { overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Board from "./Board";

const status = { board: "available", errors: { board: [] } };
const envelope = (items: unknown, dataStatus: unknown = status) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus, items });
const todo = cardDetail("Todo", { scheduled: true });
const backlog = cardDetail("Backlog", { id: "second-idea", title: "Second idea", priority: "normal" });

describe("Board", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the seven columns the API names, each card in its column, linking to its popup route", async () => {
    mockFetch({ "/api/v1/board": envelope(boardOf([todo, backlog])) });
    renderInShell(<Board />);
    await waitFor(() => expect(screen.getAllByTestId("board-column")).toHaveLength(7));
    expect(screen.getAllByTestId("board-column").map((c) => c.getAttribute("data-column"))).toEqual([...COLUMNS]);
    const column = (name: string) => within(screen.getAllByTestId("board-column").find((c) => c.getAttribute("data-column") === name)!);
    expect(column("Todo").getByRole("link", { name: /Vector search options/ })).toHaveAttribute("href", "/app/board/vault-vector-search");
    expect(column("Todo").getByText("Scheduled Tue 6 Oct")).toBeInTheDocument();
    expect(column("Backlog").getByText("Second idea")).toBeInTheDocument();
    expect(column("Done").queryAllByTestId("board-card")).toHaveLength(0);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows an empty board and an unavailable source as such", async () => {
    const dataStatus = { board: "unavailable", errors: { board: ["events.jsonl: bad"] } };
    mockFetch({ "/api/v1/board": envelope({ columns: [...COLUMNS], cards: [] }, dataStatus) });
    renderInShell(<Board />);
    await waitFor(() => expect(screen.getByTestId("data-status")).toHaveTextContent("events.jsonl: bad"));
    expect(screen.getAllByTestId("board-column")).toHaveLength(7);
  });

  it("opens the card's popup over the board for /app/board/<id>, and closing returns to the board", async () => {
    window.history.replaceState(null, "", "/app/board/vault-vector-search");
    mockFetch({ "/api/v1/board": envelope(boardOf([todo])), "/api/v1/board/vault-vector-search": envelope(todo) });
    renderInShell(<Board cardId="vault-vector-search" />);
    const dialog = await screen.findByRole("dialog", { name: "Vector search options for the vault" });
    expect(within(dialog).getByTestId("card-column")).toHaveTextContent("Todo");
    expect(screen.getAllByTestId("board-column")).toHaveLength(7);
    act(() => screen.getByRole("button", { name: "Dismiss" }).click());
    expect(window.location.pathname).toBe("/app/board");
  });

  it("names a card the API does not know instead of hanging", async () => {
    mockFetch({ "/api/v1/board": envelope(boardOf([])), "/api/v1/board/nobody": { status: 404, body: { error: "card not found" } } });
    renderInShell(<Board cardId="nobody" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404: card not found"));
  });
});
