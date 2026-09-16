export const ALL = "all";

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
  allLabel: string;
}

export default function FilterSelect({ label, value, onChange, options, allLabel }: Props) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-surface border border-border rounded px-2.5 py-1.5 text-sm text-text-2 focus:outline-none focus:border-border-2 cursor-pointer"
      aria-label={label}
    >
      {options.map((o) => (
        <option key={o} value={o} className="bg-surface-2">{o === ALL ? allLabel : o}</option>
      ))}
    </select>
  );
}
