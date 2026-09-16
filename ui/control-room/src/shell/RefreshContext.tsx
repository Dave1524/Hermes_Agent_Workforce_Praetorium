import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { AUTO_REFRESH_MS } from "@/api/useResource";

export const AUTO_REFRESH_KEY = "control-room.auto-refresh";

interface RefreshState {
  tick: number;
  autoRefresh: boolean;
  autoRefreshMs: number;
  generatedAt: string | null;
  refreshNow: () => void;
  setAutoRefresh: (on: boolean) => void;
  reportGeneratedAt: (iso: string | null) => void;
}

const RefreshContext = createContext<RefreshState | null>(null);

const readStored = (): boolean => {
  try {
    return window.localStorage.getItem(AUTO_REFRESH_KEY) !== "off";
  } catch {
    return true;
  }
};

const writeStored = (on: boolean): void => {
  try {
    window.localStorage.setItem(AUTO_REFRESH_KEY, on ? "on" : "off");
  } catch {
    /* storage may be unavailable; the toggle still works for this page load */
  }
};

export const RefreshProvider = ({ children }: { children: ReactNode }) => {
  const [tick, setTick] = useState(0);
  const [autoRefresh, setAutoRefreshState] = useState(readStored);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const refreshNow = useCallback(() => setTick((t) => t + 1), []);
  const setAutoRefresh = useCallback((on: boolean) => {
    writeStored(on);
    setAutoRefreshState(on);
  }, []);
  const reportGeneratedAt = useCallback((iso: string | null) => setGeneratedAt((prev) => (prev === iso ? prev : iso)), []);
  const value = useMemo<RefreshState>(
    () => ({ tick, autoRefresh, autoRefreshMs: autoRefresh ? AUTO_REFRESH_MS : 0, generatedAt, refreshNow, setAutoRefresh, reportGeneratedAt }),
    [tick, autoRefresh, generatedAt, refreshNow, setAutoRefresh, reportGeneratedAt],
  );
  return <RefreshContext.Provider value={value}>{children}</RefreshContext.Provider>;
};

export const useRefresh = (): RefreshState => {
  const ctx = useContext(RefreshContext);
  if (!ctx) throw new Error("useRefresh needs a RefreshProvider");
  return ctx;
};
