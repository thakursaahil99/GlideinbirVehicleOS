import { cn } from "@/utils/format";

export interface TabItem<K extends string> {
  key: K;
  label: string;
}

export function Tabs<K extends string>({ items, active, onChange }: { items: TabItem<K>[]; active: K; onChange: (k: K) => void }) {
  return (
    <div className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0" role="tablist">
      <div className="inline-flex min-w-max gap-1 rounded-xl bg-slate-200/60 p-1 ring-1 ring-inset ring-slate-200">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active === item.key}
            onClick={() => onChange(item.key)}
            className={cn(
              "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-300",
              active === item.key
                ? "bg-white text-brand-700 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/80"
                : "text-slate-500 hover:bg-white/50 hover:text-slate-800",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label, description, disabled }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex items-start justify-between gap-4", disabled && "opacity-60")}>
      <span>
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {description && <span className="block text-xs text-slate-500">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
          checked ? "bg-gradient-to-r from-brand-500 to-brand-700 shadow-[var(--shadow-glow)]" : "bg-slate-300",
        )}
      >
        <span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-300 ease-[var(--ease-spring)]", checked ? "translate-x-5" : "translate-x-0.5")} />
      </button>
    </label>
  );
}

export function Checkbox({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
      />
      {label}
    </label>
  );
}
