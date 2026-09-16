import type { ExceptionRow } from "@/api/schemas/exceptions";

export const EXCEPTION_KINDS = ["failed", "stale-input", "missing-artifact", "missed-cadence", "overdue-next-action", "unconsumed-output", "dependency-down"] as const;

export interface ExceptionView {
  kind: string;
  workflowId: string | null;
  owner: string | null;
  issue: string | null;
  failedAssertions: string[];
  requiredAction: string | null;
  runId: string | null;
  artifactUri: string | null;
  paused: boolean;
  since: string | null;
  alsoFailed: boolean;
}

export const toException = (e: ExceptionRow): ExceptionView => ({
  kind: e.kind,
  workflowId: e.workflowId ?? null,
  owner: e.owner ?? null,
  issue: e.issue ?? null,
  failedAssertions: e.failedAssertions,
  requiredAction: e.requiredAction ?? null,
  runId: e.evidence?.runId ?? null,
  artifactUri: e.evidence?.artifactUri ?? null,
  paused: e.paused ?? false,
  since: e.since ?? null,
  alsoFailed: e.alsoFailed ?? false,
});

const rank = (kind: string): number => {
  const i = (EXCEPTION_KINDS as readonly string[]).indexOf(kind);
  return i === -1 ? EXCEPTION_KINDS.length : i;
};

export const sortExceptions = (rows: ExceptionView[]): ExceptionView[] => [...rows].sort((a, b) => rank(a.kind) - rank(b.kind));

export const exceptionKindLabel = (kind: string): string =>
  (EXCEPTION_KINDS as readonly string[]).includes(kind) ? kind.charAt(0).toUpperCase() + kind.slice(1).replace(/-/g, " ") : kind;
