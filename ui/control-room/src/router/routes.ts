export const APP_BASE = "/app";

export type Route =
  | { name: "overview" }
  | { name: "workflows" }
  | { name: "workflow"; id: string }
  | { name: "run"; id: string }
  | { name: "incidents" }
  | { name: "usage" }
  | { name: "activity" }
  | { name: "agents" }
  | { name: "agent"; id: string };

export type MatchedRoute = Route & { unknown: boolean };

export const NAV_ROUTES: ReadonlyArray<{ route: Route; label: string }> = [
  { route: { name: "overview" }, label: "Overview" },
  { route: { name: "workflows" }, label: "Workflows" },
  { route: { name: "agents" }, label: "Agents" },
  { route: { name: "incidents" }, label: "Incidents" },
  { route: { name: "usage" }, label: "Usage" },
  { route: { name: "activity" }, label: "Activity" },
];

const decode = (segment: string): string => {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
};

const segmentsOf = (pathname: string): string[] | null => {
  if (pathname !== APP_BASE && !pathname.startsWith(`${APP_BASE}/`)) return null;
  return pathname.slice(APP_BASE.length).split("/").filter(Boolean);
};

const matchSegments = (segments: string[]): Route | null => {
  const [head, id, ...rest] = segments;
  if (rest.length > 0) return null;
  if (head === undefined) return { name: "overview" };
  if (id === undefined) {
    if (head === "workflows") return { name: "workflows" };
    if (head === "incidents") return { name: "incidents" };
    if (head === "usage") return { name: "usage" };
    if (head === "activity") return { name: "activity" };
    if (head === "agents") return { name: "agents" };
    return null;
  }
  if (head === "workflows") return { name: "workflow", id: decode(id) };
  if (head === "runs") return { name: "run", id: decode(id) };
  if (head === "agents") return { name: "agent", id: decode(id) };
  return null;
};

export const matchRoute = (pathname: string): MatchedRoute => {
  const segments = segmentsOf(pathname);
  const route = segments === null ? null : matchSegments(segments);
  if (route === null) return { name: "overview", unknown: true };
  return { ...route, unknown: false };
};

export const routeHref = (route: Route): string => {
  switch (route.name) {
    case "overview":
      return `${APP_BASE}/`;
    case "workflow":
      return `${APP_BASE}/workflows/${encodeURIComponent(route.id)}`;
    case "run":
      return `${APP_BASE}/runs/${encodeURIComponent(route.id)}`;
    case "agent":
      return `${APP_BASE}/agents/${encodeURIComponent(route.id)}`;
    default:
      return `${APP_BASE}/${route.name}`;
  }
};

export const isSameRoute = (a: Route, b: Route): boolean => routeHref(a) === routeHref(b);
