import { useEffect, type ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  tone?: "default" | "danger";
}

export default function DialogFrame({ title, onClose, children, footer, wide = false, tone = "default" }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={`bg-surface border ${tone === "danger" ? "border-red/40" : "border-border-2"} rounded-md shadow-xl w-full ${wide ? "max-w-3xl" : "max-w-lg"} max-h-[90vh] flex flex-col`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className={`text-sm font-semibold ${tone === "danger" ? "text-red" : "text-text"}`}>{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-text text-sm px-1" aria-label="Dismiss">
            ✕
          </button>
        </div>
        <div className="px-4 py-3 overflow-y-auto text-sm text-text-2 space-y-3">{children}</div>
        {footer && <div className="px-4 py-3 border-t border-border flex items-center justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export const buttonClass = {
  primary: "px-3 py-1.5 text-xs font-medium bg-accent-dim border border-accent/30 text-accent rounded hover:bg-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
  secondary: "px-3 py-1.5 text-xs border border-border text-text-2 rounded hover:bg-surface-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
  danger: "px-3 py-1.5 text-xs font-medium border border-red/40 text-red rounded hover:bg-red-dim transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
};

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-xs text-text-2 mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-muted mt-1">{hint}</span>}
    </label>
  );
}

export const inputClass = "w-full bg-surface-2 border border-border rounded px-2.5 py-1.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-border-2";
