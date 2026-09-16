export default function GuardsChip({ guards }: { guards: string | null }) {
  if (!guards) return null;
  return (
    <span className="font-mono px-1.5 py-0.5 rounded border text-[10px] text-amber bg-amber-dim border-amber/20 whitespace-nowrap" data-testid="guards-chip" title={guards}>
      guards
    </span>
  );
}
