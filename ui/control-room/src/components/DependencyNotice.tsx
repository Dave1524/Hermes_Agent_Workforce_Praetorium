import { type DependentView, enabledDependents } from "@/model/requires";

interface Props {
  action: "pause" | "stop";
  requiredBy: DependentView[];
  guards: string | null;
}

const VERB: Record<Props["action"], string> = { pause: "Pausing", stop: "Stopping" };

// A notice, never a refusal: the broker decides, this only says what depends on the unit.
export default function DependencyNotice({ action, requiredBy, guards }: Props) {
  const enabled = enabledDependents(requiredBy);
  if (enabled.length === 0 && !guards) return null;
  return (
    <div className="text-xs text-amber space-y-1" data-testid="dependency-notice">
      {enabled.length > 0 && (
        <p>
          {VERB[action]} this refuses every run of <span className="font-mono">{enabled.map((d) => d.workflow).join(", ")}</span> at pre-flight until it is back.
        </p>
      )}
      {guards && <p>{guards}</p>}
    </div>
  );
}
