import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarClock, CalendarDays, ClipboardCheck, Hourglass, IndianRupee, Users, Wallet, Wrench } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { reportsApi } from "@/api/operations";
import { Alert, Card, PageHeader, Skeleton, Spinner, StatsCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { RankedBars, TrendChart } from "@/features/dashboard/Charts";
import { DateRangeFilter, defaultRange } from "@/features/dashboard/DateRangeFilter";
import { useAuth } from "@/hooks/useAuth";
import { BOOKING_STATUS_LABELS, inr, timeOnly } from "@/utils/format";

import { useMyOrganization } from "./useMyOrganization";

const STATUS_MESSAGES: Record<string, { tone: "warning" | "danger" | "info"; text: string }> = {
  PENDING: { tone: "warning", text: "Your agency is awaiting Super Admin approval. You can set up services, hours and staff in the meantime." },
  SUSPENDED: { tone: "danger", text: "Your agency is suspended and cannot receive new bookings." },
  REJECTED: { tone: "danger", text: "Your agency registration was rejected." },
  INACTIVE: { tone: "info", text: "Your agency is inactive and hidden from customers." },
};

export function AgencyDashboard() {
  const { user } = useAuth();
  const { data: org, isLoading } = useMyOrganization();
  const [range, setRange] = useState(defaultRange);
  const dash = useQuery({
    queryKey: ["dashboard", "agency", range],
    queryFn: () => reportsApi.dashboard({ ...range }),
    placeholderData: keepPreviousData,
  });

  if (isLoading || !user) return <Spinner />;
  if (!org) return <Alert tone="danger">Your account is not linked to an active agency. Contact your agency admin.</Alert>;
  const notice = STATUS_MESSAGES[org.status];
  const s = dash.data?.stats ?? {};
  const c = dash.data?.charts;
  const n = (k: string) => Number(s[k] ?? 0);

  return (
    <>
      <PageHeader title={org.name} description={`${org.city}${org.state ? `, ${org.state}` : ""} · today at a glance`}
        actions={<DateRangeFilter value={range} onChange={setRange} />} />
      {notice && (
        <div className="mb-6">
          <Alert tone={notice.tone}>
            {notice.text}
            {org.status_reason && <span className="mt-1 block text-xs">Reason: {org.status_reason}</span>}
          </Alert>
        </div>
      )}

      {dash.isLoading ? <Skeleton rows={5} /> : (
        <>
          <div className="stagger grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatsCard label="Today's bookings" value={n("bookings_today")} icon={<CalendarDays className="h-5 w-5" />} />
            <StatsCard label="Upcoming" value={n("bookings_upcoming")} icon={<CalendarClock className="h-5 w-5" />} hint={`${n("bookings_pending")} awaiting confirmation`} />
            <StatsCard label="Active jobs" value={n("jobs_active")} icon={<Wrench className="h-5 w-5" />} hint={`${n("jobs_completed")} completed in period`} />
            <StatsCard label="Pending approval" value={n("bookings_pending")} icon={<Hourglass className="h-5 w-5" />} />
            <StatsCard label="Revenue today" value={inr(String(s.revenue_today ?? 0))} icon={<IndianRupee className="h-5 w-5" />} />
            <StatsCard label="Revenue this month" value={inr(String(s.revenue_month ?? 0))} icon={<IndianRupee className="h-5 w-5" />} />
            <StatsCard label="Pending payments" value={inr(String(s.pending_payments ?? 0))} icon={<Wallet className="h-5 w-5" />} />
            <StatsCard label="Customers" value={n("customers")} icon={<Users className="h-5 w-5" />} hint={`${n("vehicles")} vehicles`} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <TrendChart title="Revenue" data={c?.revenue ?? []} kind="money" />
            <TrendChart title="Bookings" data={c?.bookings ?? []} kind="count" />
            <RankedBars title="Popular services" rows={(c?.popular_services ?? []).map((p) => ({ label: p.name, value: p.bookings }))} />
            <RankedBars title="Staff utilization (hours booked)" format={(v) => `${v} h`}
              rows={(c?.staff_utilization ?? []).map((r) => ({ label: `${r.staff} · ${r.completion_rate}% done`, value: r.hours }))}
              empty="Assign technicians to bookings to see utilization." />
          </div>

          <Card title={<span className="flex items-center gap-2"><ClipboardCheck className="h-4 w-4" /> Today's schedule</span>} className="mt-6"
            actions={<Link to="/agency/calendar" className="text-sm font-medium text-brand-600 hover:text-brand-700">Open calendar</Link>}>
            {dash.data?.today?.length ? (
              <ul className="stagger divide-y divide-slate-100">
                {dash.data.today.map((b) => (
                  <li key={b.id}>
                    <Link to={`/agency/bookings/${b.id}`} className="flex items-center gap-3 rounded-xl px-1 py-2.5 hover:bg-slate-50">
                      <span className="w-16 shrink-0 font-display text-sm font-semibold text-brand-700">{timeOnly(b.start)}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-slate-900">{b.service} · {b.vehicle}</span>
                        <span className="block truncate text-xs text-slate-500">{b.customer}</span>
                      </span>
                      <StatusBadge status={b.status} label={BOOKING_STATUS_LABELS[b.status]} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">Nothing booked for today.</p>}
          </Card>
          <p className="mt-4 text-xs text-slate-400">Revenue counts settled payments net of refunds. Amounts in INR.</p>
        </>
      )}
    </>
  );
}
