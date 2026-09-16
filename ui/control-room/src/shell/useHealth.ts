import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/api/client";
import { healthResponseSchema } from "@/api/schemas/health";
import { useRefresh } from "./RefreshContext";

export type HealthStatus = "ok" | "degraded" | "unreachable" | "checking";

export interface BoxHealth {
  status: HealthStatus;
  sources: Record<string, string>;
}

// /api/v1/health answers 503 with the same JSON body when degraded; only a non-JSON or network failure is unreachable.
const degradedFromError = (e: unknown): BoxHealth => {
  if (e instanceof ApiError && e.status >= 500 && e.status < 600) {
    const parsed = healthResponseSchema.safeParse(e.body);
    if (parsed.success) return { status: "degraded", sources: parsed.data.sources };
  }
  return { status: "unreachable", sources: {} };
};

export const useHealth = (): BoxHealth => {
  const { tick, autoRefreshMs } = useRefresh();
  const [health, setHealth] = useState<BoxHealth>({ status: "checking", sources: {} });
  useEffect(() => {
    let live = true;
    const probe = () =>
      getJson("/api/v1/health", healthResponseSchema)
        .then((h) => live && setHealth({ status: h.status === "ok" ? "ok" : "degraded", sources: h.sources }))
        .catch((e: unknown) => live && setHealth(degradedFromError(e)));
    void probe();
    const id = autoRefreshMs > 0 ? setInterval(() => void probe(), autoRefreshMs) : null;
    return () => {
      live = false;
      if (id !== null) clearInterval(id);
    };
  }, [tick, autoRefreshMs]);
  return health;
};
