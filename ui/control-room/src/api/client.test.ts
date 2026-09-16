import { z } from "zod";
import { ApiError, getJson, getText, postControl, postProposal } from "./client";

const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("api client", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("getJson parses the body against the schema", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: "ok", extra: 1 }));
    const out = await getJson("/api/v1/health", z.object({ status: z.string() }));
    expect(out).toEqual({ status: "ok" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/health");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("getJson throws ApiError carrying status and body on non-2xx", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { error: "workflow not found" }));
    const err = await getJson("/api/v1/workflows/nope", z.object({})).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).body).toEqual({ error: "workflow not found" });
  });

  it("getJson throws ApiError with status 0 on a schema mismatch", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 7 }));
    const err = await getJson("/api/v1/health", z.object({ status: z.string() })).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
  });

  it("getText returns the body as text", async () => {
    fetchMock.mockResolvedValue(new Response("hello", { status: 200 }));
    expect(await getText("/runs/run-1")).toBe("hello");
  });

  it("postControl sends X-Control-Room: 1 and the body keys as given", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { receipt: { result: "previewed" }, control: { state: "paused", actions: [] } }));
    const out = await postControl({ workflow_id: "raw-ingest", action: "resume", stage: "preview", reason: "x" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/control/actions");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Control-Room")).toBe("1");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ workflow_id: "raw-ingest", action: "resume", stage: "preview", reason: "x" });
    expect(out.status).toBe(200);
    expect(out.body.receipt?.result).toBe("previewed");
  });

  it("postControl returns the refusal body instead of throwing", async () => {
    fetchMock.mockResolvedValue(jsonResponse(403, { receipt: { result: "refused", refusal: { code: "peer_denied" } }, control: null }));
    const out = await postControl({ workflow_id: "raw-ingest", action: "pause" });
    expect(out.status).toBe(403);
    expect(out.body.receipt?.refusal?.code).toBe("peer_denied");
  });

  it("postProposal sends X-Control-Room: 1 and returns status + parsed body", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { stage: "list", items: [] }));
    const out = await postProposal({ workflow_id: "raw-ingest", kind: "schedule", stage: "list" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/control/proposals");
    expect(new Headers(init?.headers).get("X-Control-Room")).toBe("1");
    expect(out.status).toBe(200);
    expect(out.body).toEqual({ stage: "list", items: [] });
  });

  it("post surfaces a non-JSON body as ApiError", async () => {
    fetchMock.mockResolvedValue(new Response("Bad Gateway", { status: 502 }));
    const err = await postControl({ workflow_id: "raw-ingest", action: "pause" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
  });
});
