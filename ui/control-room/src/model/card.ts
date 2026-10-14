import type { CardActivity } from "@/api/schemas/board";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

export const MOVE_LABELS: Record<string, string> = {
  approve_brief: "Approve brief",
  return_brief: "Return with a reason",
  approve: "Approve",
  request_changes: "Request changes",
  reject: "Reject",
  block: "Block",
  unblock: "Unblock",
  delete: "Delete",
  restore: "Restore",
};

export const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  scope: "Scope",
  deadline: "Deadline",
  research_on: "Research date",
  research_time: "Research time",
  priority: "Priority",
  tags: "Tags",
  brief: "Brief",
  notes: "Notes",
};

export const moveLabel = (move: string): string => MOVE_LABELS[move] ?? move;

const WALL_CLOCK = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/;

export const formatDay = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const wall = WALL_CLOCK.exec(iso);
  if (wall) {
    const day = formatDay(wall[1]);
    return day && `${day} ${wall[2]}`;
  }
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(date.getTime())) return null;
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
};

export const splitResearchOn = (value: string): { date: string; time: string } => {
  const [date = "", time = ""] = value.split("T");
  return { date, time };
};

export const joinResearchOn = (date: string, time: string): string => {
  if (!date.trim()) return "";
  return time.trim() ? `${date.trim()}T${time.trim()}` : date.trim();
};

export const formatResearchOn = (value: string | null | undefined): string | null => (value ? value.replace("T", " ") : null);

export const latestQuestions = (rows: readonly CardActivity[]): CardActivity | null => {
  const asked = rows.filter((row) => row.kind === "note" && row.noteKind === "questions");
  return asked.reduce<CardActivity | null>((newest, row) => (newest === null || (row.ts ?? "") > (newest.ts ?? "") ? row : newest), null);
};

const DECISION_TEXT: Record<string, string> = {
  brief_approved: "Brief approved by Dave",
  brief_returned: "Brief returned by Dave",
  approved: "Research approved by Dave",
  changes_requested: "Changes requested by Dave",
  rejected: "Rejected by Dave",
  blocked: "Blocked by Dave",
  unblocked: "Unblocked by Dave",
};

const who = (actor: string): string => (actor.startsWith("run:") ? "a run" : actor.replace(/^(mac|buzz):/, ""));
const capital = (name: string): string => name.charAt(0).toUpperCase() + name.slice(1);

const noteWord = (kind: string | null | undefined): string => {
  if (kind === "questions") return "Questions from";
  if (kind === "answer") return "Answer by";
  if (kind === "idea") return "Idea by";
  return "Note by";
};

export const activityText = (row: CardActivity): string => {
  const detail = row.detail ? `: ${row.detail}` : "";
  const decision = DECISION_TEXT[row.kind];
  if (decision) return decision + detail;
  switch (row.kind) {
    case "created":
      return `Created by ${capital(who(row.actor))}`;
    case "brief":
      return `Brief ${row.detail ?? ""} by ${capital(who(row.actor))}`.replace("  ", " ");
    case "picked":
      return `${capital(row.detail ?? "research")} run${row.outcome ? `, ${row.outcome}` : ", running"}`;
    case "note":
      return `${noteWord(row.noteKind)} ${capital(who(row.actor))}${detail}`;
    case "edited":
      return `Edited by ${capital(who(row.actor))}${detail}`;
    default:
      return `${row.kind}${detail}`;
  }
};

export const briefProvenance = (brief: { version: number; by: string; approved: boolean; approvedAt?: string | null }): string => {
  const base = `v${brief.version} by ${capital(who(brief.by))}`;
  if (!brief.approved) return base;
  const day = formatDay(brief.approvedAt);
  return day ? `${base}, approved ${day.slice(4)}` : `${base}, approved`;
};
