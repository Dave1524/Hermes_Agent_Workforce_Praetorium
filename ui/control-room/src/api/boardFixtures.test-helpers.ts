import type { Board, CardDetail } from "./schemas/board";

export const COLUMNS = ["Backlog", "Refine", "Todo", "In Progress", "In Review", "Done", "Blocked"] as const;

const LABEL_FIELDS = ["priority", "tags", "title"];
const NOT_RUNNING = [...LABEL_FIELDS, "deadline", "research_on"];
const BRIEFABLE = [...NOT_RUNNING, "brief", "idea", "notes", "scope"];

// What the read model states per column (bin/board.py EDITABLE and MOVES); the dialog renders it and keeps no copy.
export const STATED: Record<(typeof COLUMNS)[number], { editable: string[]; moves: string[] }> = {
  Backlog: { editable: BRIEFABLE, moves: ["withdraw"] },
  Refine: { editable: BRIEFABLE, moves: ["approve_brief", "return_brief", "withdraw"] },
  Todo: { editable: BRIEFABLE, moves: ["block", "withdraw"] },
  "In Progress": { editable: [...LABEL_FIELDS, "notes"], moves: [] },
  "In Review": { editable: [...NOT_RUNNING, "notes"], moves: ["approve", "request_changes", "reject"] },
  Done: { editable: ["notes"], moves: [] },
  Blocked: { editable: BRIEFABLE, moves: ["unblock", "withdraw"] },
};

export const ACTIVITY: CardDetail["activity"] = [
  { ts: "2026-09-28T10:00:00Z", kind: "brief_approved", actor: "dave" },
  { ts: "2026-09-28T09:00:00Z", kind: "brief", actor: "run:b2", runId: "b2", detail: "v2" },
  { ts: "2026-09-25T09:00:00Z", kind: "brief_returned", actor: "dave", detail: "keep it to local options" },
  { ts: "2026-09-25T08:00:00Z", kind: "brief", actor: "run:b1", runId: "b1", detail: "v1" },
  { ts: "2026-09-24T09:00:00Z", kind: "created", actor: "dave" },
];

export const cardDetail = (column: (typeof COLUMNS)[number], over: Partial<CardDetail> = {}): CardDetail => ({
  id: "vault-vector-search",
  title: "Vector search options for the vault",
  column,
  scheduled: false,
  outcome: null,
  blockedCause: null,
  approvedLanding: false,
  owner: "claudius",
  kind: "research",
  priority: "high",
  tags: ["search", "tooling"],
  deadline: "2026-10-16",
  researchOn: "2026-10-06",
  briefVersion: 2,
  exceptions: [],
  fields: {
    title: "Vector search options for the vault",
    idea: "Can the vault search run locally instead of over an API?",
    scope: ["vault:05_knowledge"],
    deadline: "2026-10-16",
    research_on: "2026-10-06",
    priority: "high",
    tags: ["search", "tooling"],
  },
  rev: 5,
  editable: STATED[column].editable,
  moves: STATED[column].moves,
  locked: ["id", "owner", "kind"],
  brief: {
    text: "# Brief: vault-vector-search\n\n## Acceptance\n\n- each option has a licence\n- one recommendation\n",
    hash: "a".repeat(64),
    version: 2,
    by: "run:b2",
    ts: "2026-09-28T09:00:00Z",
    approved: column !== "Backlog" && column !== "Refine",
    approvedAt: "2026-09-28T10:00:00Z",
    current: column !== "Backlog",
  },
  runs: [],
  activity: ACTIVITY,
  research: { status: "none", acceptance: [] },
  ...over,
});

export const boardOf = (cards: CardDetail[]): Board => ({
  columns: [...COLUMNS],
  cards: cards.map(({ fields: _f, rev: _r, editable: _e, moves: _m, locked: _l, brief: _b, runs: _u, activity: _a, research: _s, ...summary }) => summary),
});
