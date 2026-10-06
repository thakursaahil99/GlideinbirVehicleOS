import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { bookingsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import type { Booking } from "@/types/operations";
import { BOOKING_STATUS_LABELS, formatDate, inr, timeOnly } from "@/utils/format";

type Scope = "upcoming" | "past" | "all";

export function BookingsPage({ basePath }: { basePath: string }) {
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const [scope, setScope] = useState<Scope>("upcoming");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ["bookings", { scope, status, search, dateFrom, dateTo, page }],
    queryFn: () =>
      bookingsApi.list({
        upcoming: scope === "all" ? undefined : scope === "upcoming",
        ordering: scope === "upcoming" ? "start_datetime" : "-start_datetime",
        status, search, date_from: dateFrom, date_to: dateTo, page,
      }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title={isCustomer ? "My bookings" : "Bookings"}
        description={isCustomer ? "Upcoming visits and your service history." : "Every booking for your workshop."}
        actions={isCustomer && <Link to="/customer/book"><Button><CalendarPlus className="h-4 w-4" /> Book service</Button></Link>}
      />
      <Tabs items={[{ key: "upcoming", label: "Upcoming" }, { key: "past", label: "Past" }, { key: "all", label: "All" }]}
        active={scope} onChange={(k) => { setScope(k); setPage(1); }} />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Booking no., customer, reg. no…" />
          <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            {Object.entries(BOOKING_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Input aria-label="From date" type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
          <Input aria-label="To date" type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
        </div>
        <DataTable<Booking>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(b) => b.id}
          emptyTitle={scope === "upcoming" ? "No upcoming bookings" : "No bookings found"}
          columns={[
            {
              key: "when", header: "When",
              render: (b) => (
                <Link to={`${basePath}/${b.id}`} className="block min-w-0">
                  <span className="font-medium text-slate-900 hover:underline">{formatDate(b.booking_date)}</span>
                  <span className="block text-xs text-slate-500">{timeOnly(b.start_datetime)} · {b.booking_number}</span>
                </Link>
              ),
            },
            {
              key: "service", header: "Service",
              render: (b) => (
                <div className="min-w-0">
                  <p className="truncate text-slate-800">{b.service.name}</p>
                  <p className="truncate font-mono text-xs text-slate-500">{b.vehicle.registration_number}</p>
                </div>
              ),
            },
            isCustomer
              ? { key: "agency", header: "Workshop", render: (b: Booking) => b.organization.name, hideOnMobile: true }
              : { key: "customer", header: "Customer", render: (b: Booking) => b.customer.full_name, hideOnMobile: true },
            { key: "staff", header: "Technician", render: (b) => b.assigned_staff?.full_name ?? "—", hideOnMobile: true },
            { key: "price", header: "Price", render: (b) => inr(b.quoted_price), hideOnMobile: true },
            { key: "status", header: "Status", render: (b) => <StatusBadge status={b.status} label={BOOKING_STATUS_LABELS[b.status]} /> },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
    </>
  );
}
