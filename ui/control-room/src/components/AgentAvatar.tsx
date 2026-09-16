const PALETTE = ["bg-blue-dim text-blue", "bg-green-dim text-green", "bg-amber-dim text-amber", "bg-accent-dim text-accent", "bg-red-dim text-red", "bg-surface-3 text-text-2"];

const hash = (s: string): number => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);

export default function AgentAvatar({ name, size = "sm" }: { name: string | null; size?: "sm" | "md" }) {
  const sz = size === "md" ? "w-7 h-7 text-xs" : "w-5 h-5 text-[10px]";
  const tone = name ? PALETTE[hash(name.toLowerCase()) % PALETTE.length] : "bg-surface-3 text-muted";
  return (
    <div className={`rounded-full flex items-center justify-center font-semibold shrink-0 ${sz} ${tone}`} aria-hidden>
      {name ? name.charAt(0).toUpperCase() : "?"}
    </div>
  );
}
