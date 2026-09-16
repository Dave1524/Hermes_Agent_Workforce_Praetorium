import type { RequirementView } from "@/model/requires";
import RouteLink from "./RouteLink";

// A runtime unit links to its agent, a manifest unit to its workflow; anything else is plain text.
export default function RequirementLink({ requirement }: { requirement: RequirementView }) {
  const className = "text-accent hover:underline";
  if (requirement.agent) return <RouteLink to={{ name: "agent", id: requirement.agent }} className={className}>{requirement.unit}</RouteLink>;
  if (requirement.workflow) return <RouteLink to={{ name: "workflow", id: requirement.workflow }} className={className}>{requirement.unit}</RouteLink>;
  return <span className="text-text">{requirement.unit}</span>;
}
