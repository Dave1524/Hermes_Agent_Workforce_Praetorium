import type { Incident as ApiIncident } from "@/api/schemas/incidents";

export const SEVERITIES = ["critical", "high", "medium", "low", "unknown"] as const;
export type Severity = (typeof SEVERITIES)[number];

const isSeverity = (v: string): v is Severity => (SEVERITIES as readonly string[]).includes(v);

export const toSeverity = (v: string | null | undefined): Severity => (typeof v === "string" && isSeverity(v) ? v : "unknown");

export interface IncidentView {
  id: string;
  status: string;
  klass: string | null;
  severity: Severity;
  workflowId: string | null;
  agent: string | null;
  issue: string | null;
  failedAssertion: string | null;
  requiredAction: string | null;
  runId: string | null;
  evidence: string[];
  firstSeen: string | null;
  lastSeen: string | null;
  resolvedAt: string | null;
  notifiedAt: string | null;
  observations: number | null;
}

export const toIncident = (i: ApiIncident): IncidentView => ({
  id: i.id,
  status: i.status,
  klass: i.class ?? null,
  severity: toSeverity(i.severity),
  workflowId: i.workflowId ?? null,
  agent: i.agent ?? null,
  issue: i.issue ?? null,
  failedAssertion: i.failedAssertion ?? null,
  requiredAction: i.requiredAction ?? null,
  runId: i.runId ?? null,
  evidence: i.evidence,
  firstSeen: i.firstSeen ?? null,
  lastSeen: i.lastSeen ?? null,
  resolvedAt: i.resolvedAt ?? null,
  notifiedAt: i.notifiedAt ?? null,
  observations: i.observations ?? null,
});
