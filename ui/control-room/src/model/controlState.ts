export const CONTROL_STATES = ["paused", "active", "running", "unknown"] as const;
export type ControlState = (typeof CONTROL_STATES)[number];

const isControlState = (v: string): v is ControlState => (CONTROL_STATES as readonly string[]).includes(v);

export const toControlState = (v: string | null | undefined): ControlState =>
  typeof v === "string" && isControlState(v) ? v : "unknown";
