import { vi } from "vitest";

export type MockRoute = unknown | { status: number; body: unknown };

const isStatusBody = (v: unknown): v is { status: number; body: unknown } =>
  typeof v === "object" && v !== null && "status" in v && "body" in v && typeof v.status === "number";

const NOT_MOCKED = (path: string) => ({ status: 404, body: { error: `no mock for ${path}` } });

// Keyed by path (query string ignored). A route may be a single response or a queue of responses
// consumed in order; unknown paths answer a JSON 404 so a page never hangs on a missing mock.
export const mockFetch = (routes: Record<string, MockRoute | MockRoute[]>) => {
  const calls: Array<{ path: string; init: RequestInit | undefined }> = [];
  const queues = new Map(Object.entries(routes).map(([k, v]) => [k, Array.isArray(v) ? [...v] : null] as const));
  const next = (path: string): MockRoute => {
    const queue = queues.get(path);
    if (queue) return queue.length > 1 ? queue.shift() : queue[0];
    return path in routes ? routes[path] : NOT_MOCKED(path);
  };
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const path = String(input).split("?")[0]!;
    calls.push({ path, init });
    const route = next(path);
    const { status, body } = isStatusBody(route) ? route : { status: 200, body: route };
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
};
