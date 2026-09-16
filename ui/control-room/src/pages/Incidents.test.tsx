import { fireEvent, screen, waitFor } from "@testing-library/react";
import { openIncident, overview } from "@/api/fixtures.test-helpers";
import { mockFetch } from "@/api/mockFetch.test-helpers";
import { renderInShell } from "@/shell/render.test-helpers";
import Incidents from "./Incidents";

const resolved = { ...openIncident, id: "inc-0", status: "resolved", resolvedAt: "2026-09-12T00:00:00Z" };
const envelope = (items: unknown) => ({ apiVersion: "1", generatedAt: overview.generatedAt, dataStatus: { ...overview.dataStatus, incidentState: "available" }, items });

describe("Incidents", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("splits open and resolved with counts and links each to its workflow and run", async () => {
    mockFetch({ "/api/v1/incidents": envelope([openIncident, resolved]) });
    renderInShell(<Incidents />);
    await waitFor(() => expect(screen.getAllByTestId("incident")).toHaveLength(1));
    expect(screen.getByRole("tab", { name: /open/ })).toHaveTextContent("1");
    expect(screen.getByRole("link", { name: "raw-ingest" })).toHaveAttribute("href", "/app/workflows/raw-ingest");
    expect(screen.getByRole("link", { name: "run-0913" })).toHaveAttribute("href", "/app/runs/run-0913");
    expect(screen.getByLabelText("high severity")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /resolved/ }));
    expect(screen.getByText("inc-0")).toBeInTheDocument();
  });

  it("shows the data status strip when incident state is unavailable", async () => {
    mockFetch({ "/api/v1/incidents": { ...envelope([]), dataStatus: { incidentState: "unavailable", errors: { incidentState: ["no state file"] } } } });
    renderInShell(<Incidents />);
    await waitFor(() => expect(screen.getByTestId("data-status")).toHaveTextContent("incidentState unavailable"));
    expect(screen.getByTestId("data-status")).toHaveTextContent("no state file");
    expect(screen.getByText("No open incidents.")).toBeInTheDocument();
  });
});
