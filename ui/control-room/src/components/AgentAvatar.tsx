const COLORS: Record<string, string> = {
  marcus: "bg-blue-dim text-blue",
  trajan: "bg-green-dim text-green",
  claudius: "bg-amber-dim text-amber",
  augustus: "bg-accent-dim text-accent",
  aurelian: "bg-surface-3 text-muted",
};

export default function AgentAvatar({ name, size = "sm" }: { name: string | null; size?: "sm" | "md" }) {
  const key = (name ?? "").toLowerCase();
  const sz = size === "md" ? "w-7 h-7 text-xs" : "w-5 h-5 text-[10px]";
  return (
    <div className={`rounded-full flex items-center justify-center font-semibold shrink-0 ${sz} ${COLORS[key] ?? "bg-surface-3 text-text-2"}`} aria-hidden>
      {name ? name.charAt(0).toUpperCase() : "?"}
    </div>
  );
}
