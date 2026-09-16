import { useEffect, useState } from "react";
import type { z } from "zod";
import { postProposal } from "@/api/client";
import { type ProposalKind, proposalKindSchema, type proposalRecordSchema } from "@/api/schemas/proposals";
import When from "./When";

type ProposalRecord = z.infer<typeof proposalRecordSchema>;
type Listing = { status: "loading" } | { status: "ready"; items: ProposalRecord[] } | { status: "error"; message: string };

const listKind = async (workflowId: string, kind: ProposalKind): Promise<ProposalRecord[]> => {
  const { body } = await postProposal({ workflow_id: workflowId, kind, stage: "list" });
  return "stage" in body && body.stage === "list" ? body.items : [];
};

export const listProposals = async (workflowId: string): Promise<ProposalRecord[]> => {
  const perKind = await Promise.all(proposalKindSchema.options.map((kind) => listKind(workflowId, kind)));
  const byId = new Map(perKind.flat().map((p) => [p.proposal_id, p]));
  return [...byId.values()].sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""));
};

export default function ProposalsList({ workflowId, tick }: { workflowId: string; tick: number }) {
  const [listing, setListing] = useState<Listing>({ status: "loading" });
  useEffect(() => {
    let live = true;
    setListing({ status: "loading" });
    listProposals(workflowId)
      .then((items) => live && setListing({ status: "ready", items }))
      .catch((e: unknown) => live && setListing({ status: "error", message: e instanceof Error ? e.message : String(e) }));
    return () => {
      live = false;
    };
  }, [workflowId, tick]);

  if (listing.status === "loading") return <p className="text-xs text-muted" role="status">Loading proposals…</p>;
  if (listing.status === "error") return <p className="text-xs text-red" role="alert">Could not list proposals: {listing.message}</p>;
  if (listing.items.length === 0) return <p className="text-xs text-muted">No proposals recorded for this workflow.</p>;
  return (
    <ul className="space-y-1 text-xs" data-testid="proposals">
      {listing.items.map((p) => (
        <li key={p.proposal_id} className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-text-2">{p.kind ?? "?"}</span>
          <span className="font-mono text-muted">{p.stage ?? "?"}</span>
          {p.pr?.url ? (
            <a href={p.pr.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline font-mono">
              #{p.pr.number ?? "?"}
            </a>
          ) : (
            <span className="font-mono text-muted">{p.proposal_id}</span>
          )}
          {p.reason && <span className="text-text-2 truncate max-w-xs" title={p.reason}>{p.reason}</span>}
          <span className="text-muted ml-auto"><When iso={p.completed_at} /></span>
        </li>
      ))}
    </ul>
  );
}
