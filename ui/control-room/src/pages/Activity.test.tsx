import { screen, waitFor } from "@testing-library/react";
import { overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Activity from "./Activity";

const items = [
  { id: "ev-1", time: "2026-09-14T07:02:30Z", type: "run", actor: "marcus", event: "agent-inbox-sync ended: artifact", runId: "run-0914", status: "artifact" },
  { id: "ev-2", time: "2026-09-13T03:04:00Z", type: "run", actor: "claudius", event: "raw-ingest ended: failed", runId: "run-0913", status: "failed" },
];
const envelope = (list: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: overview.dataStatus, items: list });

describe("Activity", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists events newest first with run links", async () => {
    mockFetch({ "/api/v1/activity": envelope(items) });
    renderInShell(<Activity />);
    await waitFor(() => expect(screen.getAllByTestId("activity-row")).toHaveLength(2));
    expect(screen.getByRole("link", { name: "run-0913" })).toHaveAttribute("href", "/app/runs/run-0913");
    expect(screen.getByText("raw-ingest ended: failed")).toBeInTheDocument();
  });

  it("renders the empty state", async () => {
    mockFetch({ "/api/v1/activity": envelope([]) });
    renderInShell(<Activity />);
    await waitFor(() => expect(screen.getByText("No activity recorded.")).toBeInTheDocument());
  });
});
