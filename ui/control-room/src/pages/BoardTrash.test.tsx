import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { matchRoute, routeHref } from "@/router/routes";
import { renderInShell } from "@/shell/render.test-helpers";
import BoardTrash from "./BoardTrash";

const status = { board: "available", errors: { board: [] } };
const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: status, items });
const ITEMS = [
  { id: "old-question", title: "Old question", deletedAt: "2026-10-13T10:00:00Z", purgeAfter: "2026-11-12T10:00:00Z" },
  { id: "second", title: "Second", deletedAt: "2026-10-12T10:00:00Z", purgeAfter: "2026-11-11T10:00:00Z" },
];

describe("BoardTrash", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists deleted cards with when they are purged", async () => {
    mockFetch({ "/api/v1/board/trash": envelope(ITEMS) });
    renderInShell(<BoardTrash />);
    const rows = await screen.findAllByTestId("trash-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Old question");
    expect(rows[0]).toHaveTextContent(/purged/i);
  });

  it("restores a card with a signed restore and re-reads the trash", async () => {
    const { calls } = mockFetch({ "/api/v1/board/trash": envelope(ITEMS), "/api/v1/control/board": { ok: true, card: "old-question", view: null } });
    renderInShell(<BoardTrash />);
    const row = (await screen.findAllByTestId("trash-row"))[0];
    fireEvent.click(within(row).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/v1/control/board")).toHaveLength(1));
    const post = calls.find((c) => c.path === "/api/v1/control/board")!;
    expect(JSON.parse(String(post.init?.body))).toEqual({ verb: "restore", card: "old-question" });
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/v1/board/trash").length).toBeGreaterThan(1));
  });

  it("shows the broker's refusal on the row", async () => {
    mockFetch({ "/api/v1/board/trash": envelope(ITEMS), "/api/v1/control/board": { status: 409, body: { ok: false, error: "card exists: old-question" } } });
    renderInShell(<BoardTrash />);
    const row = (await screen.findAllByTestId("trash-row"))[0];
    fireEvent.click(within(row).getByRole("button", { name: "Restore" }));
    expect(await within(row).findByRole("alert")).toHaveTextContent("card exists: old-question");
  });

  it("says the trash is empty", async () => {
    mockFetch({ "/api/v1/board/trash": envelope([]) });
    renderInShell(<BoardTrash />);
    expect(await screen.findByText(/trash is empty/i)).toBeInTheDocument();
  });

  it("is /app/board/trash", () => {
    expect(matchRoute("/app/board/trash")).toEqual({ name: "trash", unknown: false });
    expect(routeHref({ name: "trash" })).toBe("/app/board/trash");
  });
});
