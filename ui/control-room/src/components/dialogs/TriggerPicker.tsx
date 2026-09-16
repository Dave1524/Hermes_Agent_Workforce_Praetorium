import { useState } from "react";
import { buttonClass } from "./DialogFrame";

export default function TriggerPicker({ choices, onPick, busy }: { choices: string[]; onPick: (trigger: string) => void; busy: boolean }) {
  const [choice, setChoice] = useState<string>(choices[0] ?? "");
  return (
    <fieldset className="bg-surface-2 border border-border rounded p-3" data-testid="trigger-picker">
      <legend className="text-xs text-text-2 px-1">This workflow has several triggers; name one</legend>
      <div className="space-y-1.5 mt-1">
        {choices.map((c) => (
          <label key={c} className="flex items-center gap-2 text-xs font-mono text-text">
            <input type="radio" name="trigger" value={c} checked={choice === c} onChange={() => setChoice(c)} className="accent-accent" />
            {c}
          </label>
        ))}
      </div>
      <div className="mt-3 flex justify-end">
        <button type="button" className={buttonClass.primary} disabled={busy || !choice} onClick={() => onPick(choice)}>
          Use {choice || "…"}
        </button>
      </div>
    </fieldset>
  );
}
