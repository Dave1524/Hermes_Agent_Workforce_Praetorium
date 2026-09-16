import type { Health } from "@/model/health";

const CONFIG: Record<Health, { label: string; dot: string; text: string; bg: string }> = {
  healthy: { label: "Healthy", dot: "bg-green", text: "text-green", bg: "bg-green-dim" },
  running: { label: "Running", dot: "bg-blue", text: "text-blue", bg: "bg-blue-dim" },
  incomplete: { label: "Incomplete", dot: "bg-amber", text: "text-amber", bg: "bg-amber-dim" },
  failed: { label: "Failed", dot: "bg-red", text: "text-red", bg: "bg-red-dim" },
  paused: { label: "Paused", dot: "bg-gray", text: "text-text-2", bg: "bg-surface-3" },
  unknown: { label: "Unknown", dot: "bg-gray", text: "text-muted", bg: "bg-surface-3" },
};

export default function HealthBadge({ health, size = "sm" }: { health: Health; size?: "sm" | "md" }) {
  const c = CONFIG[health];
  const px = size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[11px]";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded font-mono font-medium ${px} ${c.text} ${c.bg}`} data-health={health}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.dot}`} aria-hidden />
      {c.label}
    </span>
  );
}
