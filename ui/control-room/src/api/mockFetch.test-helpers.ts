import { vi } from "vitest";

export type MockRoute = unknown | { status: number; body: unknown };

const isStatusBody = (v: unknown): v is { status: number; body: unknown } =>
  typeof v === "object" && v !== null && "status" in v && "body" in v && typeof v.status === "number";

// Keyed by path (query string ignored); unknown paths answer a JSON 404 so a page never hangs on a missing mock.
export const mockFetch = (routes: Record<string, MockRoute>) => {
  const calls: Array<{ path: string; init: RequestInit | undefined }> = [];
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const path = String(input).split("?")[0]!;
    calls.push({ path, init });
    const route = routes[path];
    const { status, body } = route === undefined ? { status: 404, body: { error: `no mock for ${path}` } } : isStatusBody(route) ? route : { status: 200, body: route };
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
};
