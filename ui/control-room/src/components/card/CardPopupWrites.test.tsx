import { fireEvent, screen, waitFor } from "@testing-library/react";
import { cardDetail } from "@/api/boardFixtures.test-helpers";
import { overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { matchRoute, routeHref } from "@/router/routes";
import { renderInShell } from "@/shell/render.test-helpers";
import CardPopup from "./CardPopup";

const status = { board: "available", errors: { board: [] } };
const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: status, items });

describe("CardPopup writes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts an edit to the board seam with the rendered revision, then re-reads the card", async () => {
    const { calls } = mockFetch({
      "/api/v1/board/vault-vector-search": envelope(cardDetail("Todo")),
      "/api/v1/control/board": { ok: true, card: "vault-vector-search", view: { rev: 6 } },
    });
    renderInShell(<CardPopup cardId="vault-vector-search" />);
    fireEvent.change(await screen.findByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/v1/control/board")).toHaveLength(1));
    const post = calls.find((c) => c.path === "/api/v1/control/board")!;
    expect(post.init?.method).toBe("POST");
    expect((post.init?.headers as Record<string, string>)["X-Control-Room"]).toBe("1");
    expect(JSON.parse(String(post.init?.body))).toEqual({ verb: "edit", card: "vault-vector-search", expect_rev: 5, fields: { priority: "low" } });
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/v1/board/vault-vector-search").length).toBeGreaterThan(1));
  });

  it("shows a stale refusal from the seam", async () => {
    mockFetch({
      "/api/v1/board/vault-vector-search": envelope(cardDetail("Todo")),
      "/api/v1/control/board": { status: 409, body: { ok: false, error: "stale: card is at revision 6, you saved 5" } },
    });
    renderInShell(<CardPopup cardId="vault-vector-search" />);
    fireEvent.change(await screen.findByLabelText("Priority"), { target: { value: "low" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed while you were editing/i);
  });
});

describe("the new-card route", () => {
  it("is /app/board/new and a card id never collides with it", () => {
    expect(matchRoute("/app/board/new")).toEqual({ name: "newcard", unknown: false });
    expect(routeHref({ name: "newcard" })).toBe("/app/board/new");
    expect(matchRoute("/app/board/other")).toEqual({ name: "card", id: "other", unknown: false });
  });
});
