export default function LockNote({ name, reason }: { name: string; reason: string | null }) {
  if (!reason) return null;
  return (
    <span data-lock={name} className="block text-[11px] text-muted mt-1">
      {reason}
    </span>
  );
}
