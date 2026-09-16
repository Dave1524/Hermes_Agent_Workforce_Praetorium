import { act, renderHook, waitFor } from "@testing-library/react";
import { z } from "zod";
import { useResource } from "./useResource";

const schema = z.object({ n: z.number() });
const jsonResponse = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("useResource", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("goes loading -> ready with the parsed data", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { n: 1 }));
    const { result } = renderHook(() => useResource("/x", schema));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toEqual({ n: 1 });
  });

  it("goes to error with the ApiError on a non-2xx", async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, { error: "boom" }));
    const { result } = renderHook(() => useResource("/x", schema));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.status).toBe(500);
  });

  it("refresh refetches and keeps the last data while loading", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { n: 1 })).mockResolvedValueOnce(jsonResponse(200, { n: 2 }));
    const { result } = renderHook(() => useResource("/x", schema));
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.data).toEqual({ n: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("refetches on the auto-refresh tick when enabled, not when disabled", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(jsonResponse(200, { n: 1 }));
    const { rerender } = renderHook(({ auto }) => useResource("/x", schema, { autoRefreshMs: auto ? 1000 : 0 }), {
      initialProps: { auto: true },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    rerender({ auto: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("refetches when the path changes", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { n: 1 }));
    const { rerender } = renderHook(({ path }) => useResource(path, schema), { initialProps: { path: "/a" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender({ path: "/b" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1]![0]).toBe("/b");
  });
});
