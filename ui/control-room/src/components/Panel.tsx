import type { ReactNode } from "react";

export function Panel({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`bg-surface border border-border rounded-md p-4 ${className}`}>
      {title && <h3 className="text-xs font-semibold text-text mb-3 uppercase tracking-wider">{title}</h3>}
      {children}
    </section>
  );
}

export function SectionHeader({ title, count, countColor }: { title: string; count?: number; countColor?: string }) {
  return (
    <div className="flex items-center gap-2">
      <h2 className="text-sm font-semibold text-text">{title}</h2>
      {count !== undefined && <span className={`text-xs font-mono rounded-full px-1.5 py-0.5 ${countColor ?? "bg-surface-3 text-text-2"}`}>{count}</span>}
    </div>
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b border-border last:border-0">
      <span className="text-text-2 shrink-0">{label}</span>
      <span className="text-text font-mono text-xs pt-0.5 text-right break-all">{children}</span>
    </div>
  );
}

export function Stat({ label, value, tone = "text-text" }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="bg-surface border border-border rounded-md px-4 py-3">
      <div className={`text-2xl font-semibold leading-none font-mono ${tone}`}>{value}</div>
      <div className="text-text-2 text-xs mt-1.5">{label}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="bg-surface border border-border rounded-md p-6 text-center text-text-2 text-sm">{children}</div>;
}
