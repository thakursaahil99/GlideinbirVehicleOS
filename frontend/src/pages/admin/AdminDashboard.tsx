import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Ban, Building2, CalendarCheck2, CalendarClock, CalendarDays, Car, CheckCircle2, Clock, IndianRupee, ShieldAlert, Users, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { reportsApi } from "@/api/operations";
import { organizationsApi } from "@/api/resources";
import { catalogApi } from "@/api/services";
import { Card, PageHeader, Skeleton, StatsCard } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { RankedBars, TrendChart, formatMoney } from "@/features/dashboard/Charts";
import { DateRangeFilter, defaultRange } from "@/features/dashboard/DateRangeFilter";
import { useAuth } from "@/hooks/useAuth";
import type { Organization } from "@/types/api";
import { BOOKING_STATUS_LABELS, VEHICLE_TYPE_LABELS, formatDate, inr } from "@/utils/format";

export function AdminDashboard() {
  const { user } = useAuth();
  const [range, setRange] = useState(defaultRange);
  const [organization, setOrganization] = useState("");
  const [vehicleType, setVehicleType] = useState("");
  const [service, setService] = useState("");
  const [status, setStatus] = useState("");

  const agencies = useQuery({ queryKey: ["orgs", "all"], queryFn: () => organizationsApi.list({ page_size: 100 }) });
  const services = useQuery({ queryKey: ["catalog", "all"], queryFn: () => catalogApi.list({ page_size: 100 }) });
  const pending = useQuery({ queryKey: ["orgs", "pending-queue"], queryFn: () => organizationsApi.list({ status: "PENDING", page_size: 5, ordering: "created_at" }) });
  const filters = { ...range, organization, vehicle_type: vehicleType, service, status };
  const dash = useQuery({ queryKey: ["dashboard", "admin", filters], queryFn: () => reportsApi.dashboard(filters), placeholderData: keepPreviousData });

  const s = dash.data?.stats ?? {};
  const c = dash.data?.charts;
  const n = (k: string) => Number(s[k] ?? 0);

  return (
    <>
      <PageHeader title={`Hello, ${user?.full_name.split(" ")[0] ?? "admin"}`} description="Platform overview across every agency." />

      <Card className="mb-6">
        <div className="space-y-3">
          <DateRangeFilter value={range} onChange={setRange} />
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 [&_select]:min-w-[9rem]">
            <Select aria-label="Agency" value={organization} onChange={(e) => setOrganization(e.target.value)}>
              <option value="">All agencies</option>
              {agencies.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            <Select aria-label="Vehicle type" value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}>
              <option value="">All vehicles</option>
              {Object.entries(VEHICLE_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            <Select aria-label="Service" value={service} onChange={(e) => setService(e.target.value)}>
              <option value="">All services</option>
              {services.data?.items.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </Select>
            <Select aria-label="Booking status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {Object.entries(BOOKING_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </div>
        </div>
      </Card>

      {dash.isLoading ? <Skeleton rows={6} /> : (
        <>
          <div className="stagger grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatsCard label="Agencies" value={n("agencies_total")} icon={<Building2 className="h-5 w-5" />} hint={`${n("agencies_active")} active · ${n("agencies_pending")} pending`} />
            <StatsCard label="Customers" value={n("customers")} icon={<Users className="h-5 w-5" />} />
            <StatsCard label="Vehicles" value={n("vehicles")} icon={<Car className="h-5 w-5" />} />
            <StatsCard label="Revenue" value={inr(String(s.revenue ?? 0))} icon={<IndianRupee className="h-5 w-5" />} hint="Settled, net of refunds" />
            <StatsCard label="Today's bookings" value={n("bookings_today")} icon={<CalendarDays className="h-5 w-5" />} />
            <StatsCard label="Upcoming" value={n("bookings_upcoming")} icon={<CalendarClock className="h-5 w-5" />} />
            <StatsCard label="Completed" value={n("bookings_completed")} icon={<CheckCircle2 className="h-5 w-5" />} hint={`${n("bookings_cancelled")} cancelled`} />
            <StatsCard label="Pending payments" value={inr(String(s.pending_payments ?? 0))} icon={<Wallet className="h-5 w-5" />} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <TrendChart title="Revenue over time" data={c?.revenue ?? []} kind="money" />
            <TrendChart title="Bookings over time" data={c?.bookings ?? []} kind="count" />
            <RankedBars title="Agency performance (revenue)" format={formatMoney}
              rows={(c?.agency_performance ?? []).map((a) => ({ label: `${a.name} · ${a.bookings} bookings`, value: Number(a.revenue) }))} />
            <RankedBars title="Popular services" rows={(c?.popular_services ?? []).map((p) => ({ label: p.name, value: p.bookings }))} />
            <RankedBars title="Vehicle types" rows={(c?.vehicle_types ?? []).map((v) => ({ label: VEHICLE_TYPE_LABELS[v.type] ?? v.type, value: v.count }))} />
            <section className="animate-fade-up rounded-2xl bg-white p-4 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 sm:p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Ban className="h-4 w-4 text-slate-500" /> Cancellation rate</h3>
              <p className="mt-3 font-display text-4xl font-semibold text-slate-900">{c?.cancellation?.rate ?? 0}%</p>
              <p className="mt-1 text-sm text-slate-500">{c?.cancellation?.cancelled ?? 0} of {c?.cancellation?.total ?? 0} bookings in the period</p>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-[#5243e6] transition-all duration-700" style={{ width: `${Math.min(100, c?.cancellation?.rate ?? 0)}%` }} />
              </div>
            </section>
          </div>
        </>
      )}

      <Card className="mt-6"
        title={<span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-amber-500" /> Approval queue</span>}
        actions={<Link to="/admin/vendors?status=PENDING" className="text-sm font-medium text-brand-600 hover:text-brand-700">Review all</Link>}>
        <DataTable<Organization>
          rows={pending.data?.items}
          loading={pending.isLoading}
          rowKey={(o) => o.id}
          emptyTitle="No agencies waiting for approval"
          columns={[
            { key: "name", header: "Agency", render: (o) => <span className="font-medium text-slate-900">{o.name}</span> },
            { key: "city", header: "City", render: (o) => o.city },
            { key: "created", header: "Registered", render: (o) => formatDate(o.created_at), hideOnMobile: true },
            { key: "status", header: "Status", render: (o) => <StatusBadge status={o.status} /> },
          ]}
        />
      </Card>
      <p className="mt-4 flex items-center gap-1 text-xs text-slate-400"><Clock className="h-3 w-3" /> Figures refresh when filters change. <CalendarCheck2 className="ml-2 h-3 w-3" /> Times in IST.</p>
    </>
  );
}
