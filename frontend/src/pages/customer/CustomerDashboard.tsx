import { useQuery } from "@tanstack/react-query";
import { CalendarCheck2, CalendarPlus, Car, FileText, History, IndianRupee, Plus, Wallet } from "lucide-react";
import { Link } from "react-router";

import { reportsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader, Skeleton, StatsCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import { BOOKING_STATUS_LABELS, formatDateTime, inr } from "@/utils/format";

import { VerifyEmailBanner } from "../VerifyEmailBanner";

const QUICK = [
  { to: "/customer/vehicles", label: "Add vehicle", icon: Plus },
  { to: "/customer/book", label: "Book service", icon: CalendarPlus },
  { to: "/customer/bookings", label: "View bookings", icon: CalendarCheck2 },
  { to: "/customer/invoices", label: "View invoices", icon: FileText },
];

export function CustomerDashboard() {
  const { user } = useAuth();
  const dash = useQuery({ queryKey: ["dashboard", "customer"], queryFn: () => reportsApi.dashboard() });
  const timeline = useQuery({ queryKey: ["timeline", "me"], queryFn: () => reportsApi.timeline("me") });
  if (!user) return null;
  const s = dash.data?.stats ?? {};
  const upcoming = dash.data?.upcoming_booking;

  return (
    <>
      <PageHeader title={`Hi, ${user.full_name.split(" ")[0]}`} description="Your vehicles, bookings and payments at a glance." />
      <VerifyEmailBanner />

      <div className="stagger mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {QUICK.map((q) => (
          <Link key={q.to} to={q.to}
            className="group flex flex-col items-center gap-2 rounded-2xl bg-white p-4 text-center shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)] active:scale-[0.98]">
            <span className="rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 p-2.5 text-white shadow-[var(--shadow-glow)] transition-transform group-hover:-rotate-6">
              <q.icon className="h-5 w-5" />
            </span>
            <span className="text-sm font-medium text-slate-800">{q.label}</span>
          </Link>
        ))}
      </div>

      {dash.isLoading ? <Skeleton rows={4} /> : (
        <>
          <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatsCard label="My vehicles" value={Number(s.vehicles ?? 0)} icon={<Car className="h-5 w-5" />} />
            <StatsCard label="Upcoming bookings" value={Number(s.bookings_upcoming ?? 0)} icon={<CalendarCheck2 className="h-5 w-5" />} />
            <StatsCard label="Services completed" value={Number(s.services_completed ?? 0)} icon={<History className="h-5 w-5" />}
              hint={`${s.bookings_previous ?? 0} past bookings`} />
            <StatsCard label="Pending payments" value={inr(String(s.pending_payments ?? 0))} icon={<Wallet className="h-5 w-5" />}
              hint={`${s.invoices ?? 0} invoices · spent ${inr(String(s.total_spent ?? 0))}`} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card title="Next visit">
              {upcoming ? (
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-900">{upcoming.service}</p>
                      <p className="text-sm text-slate-500">{upcoming.agency}</p>
                    </div>
                    <StatusBadge status={upcoming.status} label={BOOKING_STATUS_LABELS[upcoming.status]} />
                  </div>
                  <p className="text-sm text-slate-700">{formatDateTime(upcoming.start)} · {upcoming.vehicle}</p>
                  <Link to={`/customer/bookings/${upcoming.id}`}><Button size="sm" variant="secondary" className="mt-2">Manage booking</Button></Link>
                </div>
              ) : (
                <div className="py-4 text-center">
                  <p className="text-sm text-slate-500">No upcoming visits.</p>
                  <Link to="/customer/book"><Button size="sm" className="mt-3"><CalendarPlus className="h-4 w-4" /> Book a service</Button></Link>
                </div>
              )}
            </Card>
            <Card title="Recent activity">
              {timeline.isLoading ? <Skeleton rows={3} /> : timeline.data?.length ? (
                <ol className="relative space-y-3 border-l border-slate-200 pl-4">
                  {timeline.data.slice(0, 6).map((e, i) => (
                    <li key={`${e.type}-${e.at}-${i}`} className="relative">
                      <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand-500 ring-4 ring-brand-100" />
                      <p className="text-sm font-medium text-slate-800">{e.title}</p>
                      <p className="text-xs text-slate-500">{e.detail} · {formatDateTime(e.at)}</p>
                    </li>
                  ))}
                </ol>
              ) : <p className="text-sm text-slate-500">Your service history will appear here.</p>}
            </Card>
          </div>
          {Number(s.pending_payments ?? 0) > 0 && (
            <Link to="/customer/invoices" className="mt-6 flex items-center gap-3 rounded-2xl bg-gradient-to-r from-brand-600 to-accent-500 p-4 text-white shadow-[var(--shadow-glow)]">
              <IndianRupee className="h-5 w-5" />
              <span className="flex-1 text-sm font-medium">You have {inr(String(s.pending_payments))} to pay. Pay online in a few taps.</span>
              <span className="text-sm font-semibold">Pay →</span>
            </Link>
          )}
        </>
      )}
    </>
  );
}
