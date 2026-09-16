export const ROLES = ["agent-workflow", "system-workflow", "agent-runtime"] as const;
export type Role = (typeof ROLES)[number] | "unknown";

const isRole = (v: string): v is (typeof ROLES)[number] => (ROLES as readonly string[]).includes(v);

export const toRole = (v: string | null | undefined): Role => (typeof v === "string" && isRole(v) ? v : "unknown");

export const ROLE_LABELS: Record<Role, string> = {
  "agent-workflow": "Agent workflow",
  "system-workflow": "System workflow",
  "agent-runtime": "Agent runtime",
  unknown: "Unknown",
};
