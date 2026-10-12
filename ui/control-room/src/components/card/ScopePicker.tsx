import { useState } from "react";
import { inputClass } from "@/components/dialogs/DialogFrame";
import { listOf } from "@/model/cardDraft";
import { SCOPE_PATTERN, matchingScopes } from "@/model/scopeOptions";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export default function ScopePicker({ value, onChange }: Props) {
  const chosen = listOf(value);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const options = matchingScopes(query, chosen);
  const typed = query.trim();
  const canAddTyped = SCOPE_PATTERN.test(typed) && !chosen.includes(typed);
  const publish = (next: string[]) => onChange(next.join(", "));
  const add = (scope: string) => {
    publish([...chosen, scope]);
    setQuery("");
  };
  const commitTyped = () => canAddTyped && add(typed);
  return (
    <div className="space-y-1.5">
      {chosen.length > 0 && (
        <span className="flex gap-1.5 flex-wrap">
          {chosen.map((scope) => (
            <span key={scope} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-2 text-text-2 font-mono">
              {scope}
              <button type="button" aria-label={`Remove ${scope}`} className="text-muted hover:text-text" onClick={() => publish(chosen.filter((s) => s !== scope))}>
                ✕
              </button>
            </span>
          ))}
        </span>
      )}
      <div className="relative">
        <input
          aria-label="Scope"
          className={inputClass}
          value={query}
          placeholder="Search folders and repos, or type vault:… / repo:…"
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== ",") return;
            e.preventDefault();
            if (canAddTyped) return commitTyped();
            if (options.length > 0 && typed !== "") add(options[0]);
          }}
        />
        {open && (options.length > 0 || canAddTyped) && (
          <ul role="listbox" aria-label="Scope suggestions" className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto bg-surface border border-border-2 rounded shadow-xl">
            {canAddTyped && !options.includes(typed) && (
              <li role="option" aria-selected={false} className="px-2.5 py-1 font-mono cursor-pointer hover:bg-surface-3" onMouseDown={(e) => (e.preventDefault(), add(typed))}>
                Add “{typed}”
              </li>
            )}
            {options.map((o) => (
              <li key={o} role="option" aria-selected={false} className="px-2.5 py-1 font-mono cursor-pointer hover:bg-surface-3" onMouseDown={(e) => (e.preventDefault(), add(o))}>
                {o}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
