import { ChevronRight, LayoutGrid, LogOut, Menu, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, matchPath, useLocation, useNavigate } from "react-router";

import { BuiltBy } from "@/components/BuiltBy";
import { Logo } from "@/components/Logo";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { useAuth } from "@/hooks/useAuth";
import { ROLE_LABELS, cn } from "@/utils/format";

import { NAVIGATION, type NavItem } from "./navigation";

const AREA_LABELS: Record<keyof typeof NAVIGATION, string> = {
  admin: "Platform",
  agency: "Workshop",
  customer: "My garage",
};

function initials(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-accent-500 font-semibold text-white ring-2 ring-white/20",
        className,
      )}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

export function AppLayout({ area }: { area: keyof typeof NAVIGATION }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  if (!user) return null;
  const items = NAVIGATION[area].filter(
    (item) => (!item.roles || item.roles.includes(user.role)) && (!item.permission || user.permissions.includes(item.permission)),
  );
  // Most specific nav entry matching the current URL, for the header title.
  const current = [...items]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => matchPath({ path: item.to, end: Boolean(item.end) }, location.pathname));
  // Phones get the first few destinations as a bottom tab bar; the rest stay in the drawer.
  const tabItems = items.slice(0, 4);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const navLink = (item: NavItem) => (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
          isActive
            ? "bg-gradient-to-r from-white/[0.12] to-white/[0.03] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]"
            : "text-slate-400 hover:translate-x-0.5 hover:bg-white/[0.05] hover:text-white",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              "absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-accent-400 to-brand-500 transition-all duration-300",
              isActive ? "opacity-100" : "scale-y-0 opacity-0",
            )}
            aria-hidden
          />
          <span
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-300",
              isActive ? "bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-[var(--shadow-glow)]" : "bg-white/[0.04] group-hover:bg-white/[0.08]",
            )}
          >
            <item.icon className="h-4 w-4" aria-hidden />
          </span>
          <span className="truncate">{item.label}</span>
        </>
      )}
    </NavLink>
  );

  const sidebar = (
    <nav className="relative flex h-full flex-col overflow-hidden bg-ink-900 px-3 py-5">
      {/* Ambient glows */}
      <span className="pointer-events-none absolute -left-20 -top-24 h-64 w-64 rounded-full bg-brand-600/30 blur-3xl" aria-hidden />
      <span className="pointer-events-none absolute -bottom-24 -right-16 h-56 w-56 rounded-full bg-accent-500/15 blur-3xl" aria-hidden />

      <div className="relative px-2 pb-7">
        <Logo light />
      </div>
      <p className="relative px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">{AREA_LABELS[area]}</p>
      <ul className="stagger relative -mx-1 flex-1 space-y-1 overflow-y-auto px-1">
        {items.map((item) => (
          <li key={item.to}>{navLink(item)}</li>
        ))}
      </ul>

      <div className="relative mt-4 rounded-2xl bg-white/[0.05] p-3 ring-1 ring-inset ring-white/[0.08]">
        <div className="flex items-center gap-3">
          <Avatar name={user.full_name} className="h-9 w-9 text-xs" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{user.full_name}</p>
            <p className="truncate text-xs text-slate-400">{ROLE_LABELS[user.role]}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Log out"
            title="Log out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
      <p className="relative px-3 pt-3 text-[11px] text-slate-500">
        Built by <span className="font-semibold text-slate-200">Sahil Thakur</span>
      </p>
    </nav>
  );

  return (
    <div className="app-canvas flex min-h-full">
      {/* Desktop sidebar */}
      <aside className="hidden w-72 shrink-0 lg:block">
        <div className="fixed inset-y-0 w-72">{sidebar}</div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 animate-fade-in bg-slate-950/60 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <div className="relative h-full w-72 max-w-[85%] animate-slide-in-left shadow-2xl">
            {sidebar}
            <button
              type="button"
              className="absolute right-3 top-4 rounded-lg p-1.5 text-slate-400 transition-all hover:rotate-90 hover:bg-white/10 hover:text-white"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200/70 bg-white/70 px-4 backdrop-blur-xl sm:px-6">
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-600 transition-colors hover:bg-slate-100 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <nav aria-label="Breadcrumb" className="hidden items-center gap-1.5 text-sm text-slate-400 md:flex">
              <span>{AREA_LABELS[area]}</span>
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            </nav>
            <span key={current?.to} className="animate-fade-in truncate font-display text-sm font-semibold text-slate-900 sm:text-base">
              {current?.label ?? "Overview"}
            </span>
            {user.organization && (
              <span className="ml-2 hidden min-w-0 items-center gap-2 border-l border-slate-200 pl-3 sm:flex">
                <span className="truncate text-sm text-slate-600">{user.organization.name}</span>
                <StatusBadge status={user.organization.status} />
              </span>
            )}
          </div>
          <div className="flex items-center">
            <NavLink
              to={`/${area}/search`}
              aria-label="Search"
              title="Search"
              className={({ isActive }) =>
                cn(
                  "inline-flex h-10 w-10 items-center justify-center rounded-xl transition hover:bg-slate-100",
                  isActive ? "bg-brand-50 text-brand-700" : "text-slate-600",
                )
              }
            >
              <Search className="h-5 w-5" />
            </NavLink>
            <NotificationBell />
          </div>
          <div className="hidden border-l border-slate-200 pl-3 text-right sm:block">
            <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
            <p className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</p>
          </div>
          <Avatar name={user.full_name} className="h-9 w-9 text-xs ring-brand-100" />
          <button
            type="button"
            onClick={handleLogout}
            className="hidden items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Log out
          </button>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-28 sm:px-6 sm:py-8 lg:px-8 lg:pb-8">
          <div key={location.pathname} className="animate-fade-up">
            <Outlet />
          </div>
        </main>

        <footer className="hidden border-t border-slate-200/70 bg-white/60 px-4 py-3 backdrop-blur sm:px-6 lg:block">
          <BuiltBy />
        </footer>
      </div>

      {/* Mobile bottom tab bar */}
      <nav
        className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 flex animate-fade-up items-stretch justify-around rounded-2xl bg-ink-900/95 p-1.5 shadow-2xl ring-1 ring-white/10 backdrop-blur-xl lg:hidden"
        aria-label="Quick navigation"
      >
        {tabItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium transition-all duration-200 active:scale-95",
                isActive ? "bg-white/10 text-white" : "text-slate-400",
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon className={cn("h-5 w-5 transition-transform duration-300", isActive && "-translate-y-0.5 text-accent-400")} aria-hidden />
                <span className="w-full truncate text-center">{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium text-slate-400 transition-all active:scale-95"
        >
          <LayoutGrid className="h-5 w-5" aria-hidden />
          More
        </button>
      </nav>
    </div>
  );
}
