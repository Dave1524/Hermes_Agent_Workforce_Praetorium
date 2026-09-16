import type { ControlState } from "@/model/controlState";

const STYLE: Record<ControlState, string> = {
  paused: "text-text-2 bg-surface-3 border-border",
  active: "text-green bg-green-dim border-green/20",
  running: "text-blue bg-blue-dim border-blue/20",
  unknown: "text-muted bg-surface-3 border-border",
};

export default function ControlStateBadge({ state }: { state: ControlState }) {
  return <span className={`font-mono px-1.5 py-0.5 rounded border text-[10px] ${STYLE[state]}`} data-control={state}>{state}</span>;
}
