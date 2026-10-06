import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { reportsApi } from "@/api/operations";
import { Card, Skeleton } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { BOOKING_STATUS_LABELS, formatDateTime, inr } from "@/utils/format";

/** Spending, bookings and the service timeline on a customer's profile (scoped to the viewer's agency by the API). */
export function CustomerInsights({ bookingsBase }: { bookingsBase: string }) {
  const { id = "" } = useParams();
  const summary = useQuery({ queryKey: ["customers", id, "summary"], queryFn: () => reportsApi.customerSummary(id) });
  const timeline = useQuery({ queryKey: ["customers", id, "timeline"], queryFn: () => reportsApi.timeline(id) });
  const s = summary.data;

  return (
    <>
      <Card title="Service summary" className="lg:col-span-1">
        {summary.isLoading ? <Skeleton rows={3} /> : s && (
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-xs text-slate-500">Total spending</dt><dd className="font-display text-lg font-semibold text-slate-900">{inr(s.total_spending)}</dd></div>
            <div><dt className="text-xs text-slate-500">Pending payments</dt><dd className="font-display text-lg font-semibold text-slate-900">{inr(s.pending_payments)}</dd></div>
            <div><dt className="text-xs text-slate-500">Bookings</dt><dd className="font-medium">{s.bookings_count}</dd></div>
            <div><dt className="text-xs text-slate-500">Completed services</dt><dd className="font-medium">{s.completed_services}</dd></div>
          </dl>
        )}
      </Card>
      <Card title="Bookings" className="lg:col-span-2">
        {summary.isLoading ? <Skeleton rows={3} /> : (
          <ul className="divide-y divide-slate-100">
            {[...(s?.upcoming_bookings ?? []), ...(s?.booking_history ?? [])].slice(0, 8).map((b) => (
              <li key={b.id}>
                <Link to={`${bookingsBase}/${b.id}`} className="flex items-center gap-3 rounded-xl px-1 py-2.5 hover:bg-slate-50">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-900">{b.service.name} · {b.vehicle.registration_number}</span>
                    <span className="block text-xs text-slate-500">{formatDateTime(b.start_datetime)} · {b.booking_number}</span>
                  </span>
                  <StatusBadge status={b.status} label={BOOKING_STATUS_LABELS[b.status]} />
                </Link>
              </li>
            ))}
            {!s?.bookings_count && <li className="py-3 text-sm text-slate-500">No bookings yet.</li>}
          </ul>
        )}
      </Card>
      <Card title="Timeline" className="lg:col-span-3">
        {timeline.isLoading ? <Skeleton rows={4} /> : timeline.data?.length ? (
          <ol className="relative space-y-4 border-l border-slate-200 pl-4">
            {timeline.data.slice(0, 30).map((e, i) => (
              <li key={`${e.type}-${e.at}-${i}`} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand-500 ring-4 ring-brand-100" />
                <p className="text-sm font-medium text-slate-800">{e.title}</p>
                <p className="text-xs text-slate-500">{e.detail} · {formatDateTime(e.at)}</p>
              </li>
            ))}
          </ol>
        ) : <p className="text-sm text-slate-500">No activity yet.</p>}
      </Card>
    </>
  );
}
