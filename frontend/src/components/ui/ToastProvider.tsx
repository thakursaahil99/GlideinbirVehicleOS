import { CheckCircle2, Info, XCircle } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";

import { cn } from "@/utils/format";

import { ToastContext, type ToastTone } from "./toast-context";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const icons = { success: CheckCircle2, error: XCircle, info: Info };
const tones = {
  success: "ring-emerald-200 text-emerald-800",
  error: "ring-rose-200 text-rose-800",
  info: "ring-slate-200 text-slate-800",
};

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const show = useCallback((message: string, tone: ToastTone = "info") => {
    const id = nextId++;
    setItems((prev) => [...prev, { id, message, tone }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4500);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-[max(1rem,env(safe-area-inset-bottom))] z-[60] flex flex-col items-center gap-2 px-4 sm:items-end sm:pr-6" aria-live="polite">
        {items.map((t) => {
          const Icon = icons[t.tone];
          return (
            <div key={t.id} className={cn("pointer-events-auto flex w-full max-w-sm animate-toast-in items-start gap-2.5 rounded-xl bg-white/95 px-4 py-3 text-sm shadow-[var(--shadow-lift)] ring-1 backdrop-blur", tones[t.tone])}>
              <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{t.message}</span>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
