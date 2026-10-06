import { AlertTriangle, CheckCircle2, Inbox, Info, XCircle } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/utils/format";

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section
      className={cn(
        "animate-fade-up rounded-2xl bg-white/90 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 backdrop-blur-sm transition-shadow duration-300 hover:shadow-[var(--shadow-lift)]",
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3.5 sm:px-5">
          {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  );
}

/** Animates a number from 0 to `value` once it mounts. */
function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  const frame = useRef(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const duration = 900;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [value]);

  return <>{shown.toLocaleString("en-IN")}</>;
}

export function StatsCard({ label, value, icon, hint }: { label: string; value: ReactNode; icon?: ReactNode; hint?: string }) {
  return (
    <div className="group relative overflow-hidden rounded-2xl bg-white p-4 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)] sm:p-5">
      {/* Corner glow that brightens on hover */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br from-brand-400/20 to-accent-400/20 blur-2xl transition-opacity duration-500 group-hover:opacity-100 sm:opacity-60"
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
          <p className="mt-2 break-words font-display text-2xl font-semibold tabular-nums leading-tight text-slate-900">
            {typeof value === "number" ? <CountUp value={value} /> : value}
          </p>
          {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
        </div>
        {icon && (
          <div className="rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 p-2.5 text-white shadow-[var(--shadow-glow)] transition-transform duration-500 ease-[var(--ease-spring)] group-hover:-rotate-6 group-hover:scale-110">
            {icon}
          </div>
        )}
      </div>
      <span
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-0.5 origin-left scale-x-0 bg-gradient-to-r from-brand-500 to-accent-400 transition-transform duration-500 group-hover:scale-x-100"
      />
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex animate-fade-up flex-wrap items-end justify-between gap-3 sm:mb-8">
      <div className="min-w-0">
        <h1 className="bg-gradient-to-r from-slate-900 via-slate-800 to-brand-700 bg-clip-text text-2xl font-semibold text-transparent sm:text-3xl">
          {title}
        </h1>
        {description && <p className="mt-1.5 text-sm text-slate-500">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex animate-fade-in items-center justify-center gap-3 py-12 text-sm text-slate-500" role="status">
      <span className="relative flex h-5 w-5">
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600" />
        <span className="absolute inset-1.5 rounded-full bg-gradient-to-br from-brand-500 to-accent-400" />
      </span>
      {label}
    </div>
  );
}

/** Shimmering placeholder rows while a list loads. */
export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 py-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="skeleton h-9 w-9 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3" style={{ width: `${70 - i * 8}%` }} />
            <div className="skeleton h-2.5 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex animate-fade-up flex-col items-center py-12 text-center">
      <div className="relative mb-4">
        <span className="absolute inset-0 rounded-2xl bg-brand-400/20 blur-xl" aria-hidden />
        <div className="relative flex h-14 w-14 animate-float items-center justify-center rounded-2xl bg-gradient-to-br from-brand-50 to-white text-brand-600 ring-1 ring-brand-100">
          <Inbox className="h-6 w-6" aria-hidden />
        </div>
      </div>
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>}
    </div>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "warning" | "danger" | "success"; children: ReactNode }) {
  const tones = {
    info: { box: "bg-brand-50/80 text-brand-900 ring-brand-200 before:bg-brand-500", Icon: Info, icon: "text-brand-600" },
    warning: { box: "bg-amber-50/80 text-amber-900 ring-amber-200 before:bg-amber-500", Icon: AlertTriangle, icon: "text-amber-600" },
    danger: { box: "bg-rose-50/80 text-rose-900 ring-rose-200 before:bg-rose-500", Icon: XCircle, icon: "text-rose-600" },
    success: { box: "bg-emerald-50/80 text-emerald-900 ring-emerald-200 before:bg-emerald-500", Icon: CheckCircle2, icon: "text-emerald-600" },
  }[tone];
  return (
    <div
      className={cn(
        "relative flex animate-fade-up gap-3 overflow-hidden rounded-xl py-3 pl-5 pr-4 text-sm ring-1",
        "before:absolute before:inset-y-0 before:left-0 before:w-1",
        tones.box,
      )}
    >
      <tones.Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tones.icon)} aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
