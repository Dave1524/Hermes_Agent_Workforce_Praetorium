import { useCallback, useEffect, useRef, useState } from "react";
import type { z } from "zod";
import { ApiError, getJson } from "./client";

export type ResourceStatus = "loading" | "ready" | "error";

export interface Resource<T> {
  status: ResourceStatus;
  data: T | null;
  error: ApiError | null;
  refresh: () => Promise<void>;
}

export const AUTO_REFRESH_MS = 60_000;

const toApiError = (e: unknown): ApiError =>
  e instanceof ApiError ? e : new ApiError(0, null, e instanceof Error ? e.message : String(e));

export const useResource = <T extends z.ZodType>(
  path: string,
  schema: T,
  options: { autoRefreshMs?: number } = {},
): Resource<z.infer<T>> => {
  const autoRefreshMs = options.autoRefreshMs ?? 0;
  const [status, setStatus] = useState<ResourceStatus>("loading");
  const [data, setData] = useState<z.infer<T> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const mine = ++generation.current;
    setStatus("loading");
    try {
      const next = await getJson(path, schema);
      if (mine !== generation.current) return;
      setData(next);
      setError(null);
      setStatus("ready");
    } catch (e) {
      if (mine !== generation.current) return;
      setError(toApiError(e));
      setStatus("error");
    }
  }, [path, schema]);

  useEffect(() => {
    void refresh();
    return () => {
      generation.current++;
    };
  }, [refresh]);

  useEffect(() => {
    if (autoRefreshMs <= 0) return;
    const id = setInterval(() => void refresh(), autoRefreshMs);
    return () => clearInterval(id);
  }, [refresh, autoRefreshMs]);

  return { status, data, error, refresh };
};
