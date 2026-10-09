import type { CardDetail } from "@/api/schemas/board";

export interface Draft {
  title: string;
  idea: string;
  brief: string;
  research_on: string;
  deadline: string;
  priority: string;
  tags: string;
  scope: string;
  note: string;
}

export interface Editing {
  draft: Draft;
  set: (name: keyof Draft, value: string) => void;
}

export const DETAIL_FIELDS = ["title", "idea", "scope", "priority", "tags", "research_on", "deadline"] as const;
const LIST_FIELDS = new Set<string>(["tags", "scope"]);

export const listOf = (text: string): string[] =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

export const draftOf = (card: CardDetail): Draft => ({
  title: card.fields.title,
  idea: card.fields.idea,
  brief: card.brief?.text ?? "",
  research_on: card.fields.research_on ?? "",
  deadline: card.fields.deadline ?? "",
  priority: card.fields.priority ?? "normal",
  tags: card.fields.tags.join(", "),
  scope: card.fields.scope.join(", "),
  note: "",
});

const valueOf = (name: (typeof DETAIL_FIELDS)[number], text: string): unknown => {
  if (LIST_FIELDS.has(name)) return listOf(text);
  if (name === "research_on" || name === "deadline") return text.trim() === "" ? null : text.trim();
  return text.trim();
};

export const changesOf = (base: Draft, draft: Draft, editable: readonly string[]): Record<string, unknown> => {
  const changes: Record<string, unknown> = {};
  for (const name of DETAIL_FIELDS) {
    if (!editable.includes(name)) continue;
    const next = valueOf(name, draft[name]);
    if (JSON.stringify(next) !== JSON.stringify(valueOf(name, base[name]))) changes[name] = next;
  }
  return changes;
};

export const briefChanged = (base: Draft, draft: Draft): boolean => draft.brief.trim() !== "" && draft.brief.trim() !== base.brief.trim();

export const isDirty = (base: Draft, draft: Draft, editable: readonly string[]): boolean =>
  Object.keys(changesOf(base, draft, editable)).length > 0 || briefChanged(base, draft) || draft.note.trim() !== "";

export const lockReason = (card: CardDetail, name: string): string | null => {
  if (card.editable.includes(name)) return null;
  if (card.column === "Done") return "Locked: the card is closed";
  if (card.column === "In Progress") return "Locked while a run works on the card";
  if ((name === "idea" || name === "scope") && card.runs.some((run) => run.purpose === "research")) return "Locked after the first research run";
  return `Locked in ${card.column}`;
};

export const NEW_CARD_FIELDS = ["title", "idea", "scope", "priority", "tags", "research_on", "deadline", "brief"];

export const emptyCard = (): CardDetail => ({
  id: "",
  title: "",
  column: "Backlog",
  scheduled: false,
  outcome: null,
  blockedCause: null,
  approvedLanding: false,
  owner: "claudius",
  kind: "research",
  priority: "normal",
  tags: [],
  deadline: null,
  researchOn: null,
  briefVersion: 0,
  exceptions: [],
  fields: { title: "", idea: "", scope: [], deadline: null, research_on: null, priority: "normal", tags: [] },
  rev: 0,
  editable: NEW_CARD_FIELDS,
  moves: [],
  locked: ["id", "owner", "kind"],
  brief: null,
  runs: [],
  activity: [],
  research: { status: "none", acceptance: [] },
});
