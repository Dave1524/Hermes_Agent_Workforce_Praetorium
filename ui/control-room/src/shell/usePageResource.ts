import { useEffect } from "react";
import type { z } from "zod";
import { type Resource, useResource } from "@/api/useResource";
import { useRefresh } from "./RefreshContext";

// A page's primary resource follows the shell's refresh tick and auto-refresh setting and reports generatedAt.
export const usePageResource = <T extends z.ZodType<{ generatedAt: string }>>(path: string, schema: T): Resource<z.infer<T>> => {
  const { tick, autoRefreshMs, reportGeneratedAt } = useRefresh();
  const resource = useResource(path, schema, { tick, autoRefreshMs });
  const generatedAt = resource.data?.generatedAt ?? null;
  useEffect(() => {
    if (generatedAt) reportGeneratedAt(generatedAt);
  }, [generatedAt, reportGeneratedAt]);
  return resource;
};

export const useSecondaryResource = <T extends z.ZodType>(path: string, schema: T): Resource<z.infer<T>> => {
  const { tick, autoRefreshMs } = useRefresh();
  return useResource(path, schema, { tick, autoRefreshMs });
};
