import { CarFront } from "lucide-react";

import { cn } from "@/utils/format";

export const APP_NAME = "Glideinbir";
export const APP_TAGLINE = "Vehicle Operating System";
export const APP_DESCRIPTION =
  "One platform to run vehicle service workshops: bookings, job cards, spare parts, payments and invoices for cars, bikes, scooters and EVs, with customers kept in the loop at every step.";

export function Logo({ light = false, describe = false }: { light?: boolean; describe?: boolean }) {
  return (
    <span className="block">
      <span className="group flex items-center gap-2.5">
        <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 via-brand-600 to-accent-500 text-white shadow-[var(--shadow-glow)] transition-transform duration-500 ease-[var(--ease-spring)] group-hover:-rotate-6 group-hover:scale-105">
          <CarFront className="h-5 w-5" aria-hidden />
          <span className="absolute inset-0 rounded-xl ring-1 ring-inset ring-white/25" />
        </span>
        <span className="min-w-0 leading-tight">
          <span className={cn("block font-display text-[17px] font-bold tracking-tight", light ? "text-white" : "text-slate-900")}>{APP_NAME}</span>
          <span className={cn("block whitespace-nowrap text-[9.5px] font-semibold uppercase tracking-[0.16em]", light ? "text-accent-400" : "text-brand-600")}>
            {APP_TAGLINE}
          </span>
        </span>
      </span>
      {describe && (
        <span className={cn("mt-3 block max-w-md text-sm leading-relaxed", light ? "text-slate-300" : "text-slate-500")}>{APP_DESCRIPTION}</span>
      )}
    </span>
  );
}
