import { Bike, CalendarCheck2, CarFront, ShieldCheck, Sparkles, Wrench, Zap } from "lucide-react";
import { Outlet } from "react-router";

import { BuiltBy } from "@/components/BuiltBy";
import { Logo } from "@/components/Logo";

const FEATURES = [
  { icon: CalendarCheck2, text: "Smart bookings & slot planning" },
  { icon: Wrench, text: "Job cards, parts & live progress" },
  { icon: ShieldCheck, text: "Every agency's data strictly isolated" },
];

/** Decorative "live workshop" cards floating over the hero. */
function FloatingCards() {
  return (
    <div className="pointer-events-none relative mx-auto h-56 w-full max-w-md" aria-hidden>
      <div className="absolute left-0 top-2 w-64 animate-float rounded-2xl bg-white/10 p-4 shadow-2xl ring-1 ring-white/15 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600">
            <CarFront className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Job card #1042</p>
            <p className="text-xs text-slate-300">Hyundai Creta · General service</p>
          </div>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
          <div className="h-full w-3/4 animate-gradient-pan rounded-full bg-gradient-to-r from-accent-400 via-brand-400 to-accent-400 bg-[length:200%_100%]" />
        </div>
        <p className="mt-1.5 text-[11px] text-slate-300">Work in progress · 75%</p>
      </div>

      <div
        className="absolute right-0 top-24 w-56 animate-float rounded-2xl bg-white/10 p-4 shadow-2xl ring-1 ring-white/15 backdrop-blur-md"
        style={{ animationDelay: "-3s" }}
      >
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600">
            <Bike className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-medium">Ready for pickup</p>
            <p className="text-xs text-slate-300">Royal Enfield Classic 350</p>
          </div>
        </div>
      </div>

      <div
        className="absolute bottom-0 left-10 flex animate-float items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs shadow-xl ring-1 ring-white/15 backdrop-blur-md"
        style={{ animationDelay: "-1.5s" }}
      >
        <Zap className="h-3.5 w-3.5 text-amber-300" />
        EV battery check booked · 10:30 AM
      </div>
    </div>
  );
}

export function AuthLayout() {
  return (
    <div className="flex min-h-full bg-white">
      <div className="relative hidden w-1/2 flex-col justify-between gap-8 overflow-hidden bg-ink-900 p-10 text-white lg:flex xl:p-14">
        {/* Animated gradient glows */}
        <span className="pointer-events-none absolute -left-24 -top-24 h-96 w-96 animate-blob rounded-full bg-brand-600/40 blur-3xl" aria-hidden />
        <span
          className="pointer-events-none absolute -bottom-32 right-0 h-96 w-96 animate-blob rounded-full bg-accent-500/25 blur-3xl"
          style={{ animationDelay: "-6s" }}
          aria-hidden
        />
        <span
          className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(white_1px,transparent_1px),linear-gradient(90deg,white_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]"
          aria-hidden
        />

        <div className="relative animate-fade-up">
          <Logo light describe />
        </div>

        <div className="relative space-y-8">
          <div className="animate-fade-up" style={{ animationDelay: "100ms" }}>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-accent-400 ring-1 ring-white/15">
              <Sparkles className="h-3.5 w-3.5" /> Cars · Bikes · Scooters · EVs
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.15] xl:text-5xl">
              One platform for every{" "}
              <span className="animate-gradient-pan bg-gradient-to-r from-accent-400 via-brand-300 to-accent-400 bg-[length:200%_auto] bg-clip-text text-transparent">
                workshop
              </span>
              , vehicle and customer.
            </h1>
          </div>

          <FloatingCards />

          <ul className="stagger hidden space-y-3 [@media(min-height:1000px)]:block">
            {FEATURES.map((f) => (
              <li key={f.text} className="flex items-center gap-3 text-sm text-slate-300">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.07] text-accent-400 ring-1 ring-white/10">
                  <f.icon className="h-4 w-4" />
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-sm text-slate-400">
          Built by <span className="font-semibold text-white">Sahil Thakur</span>
        </p>
      </div>

      <div className="relative flex flex-1 flex-col">
        {/* Soft brand glow behind the form on every screen size */}
        <span className="pointer-events-none absolute right-0 top-0 h-72 w-72 rounded-full bg-brand-400/10 blur-3xl" aria-hidden />
        <span className="pointer-events-none absolute bottom-0 left-0 h-60 w-60 rounded-full bg-accent-400/10 blur-3xl lg:hidden" aria-hidden />
        <div className="relative flex flex-1 items-center justify-center px-4 py-10 sm:px-6">
          <div className="w-full max-w-md animate-fade-up">
            <div className="mb-8 lg:hidden">
              <Logo describe />
            </div>
            <Outlet />
          </div>
        </div>
        <footer className="relative px-4 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] text-center lg:hidden">
          <BuiltBy />
        </footer>
      </div>
    </div>
  );
}
