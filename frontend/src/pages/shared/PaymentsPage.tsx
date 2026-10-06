import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { paymentsApi } from "@/api/operations";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/FormField";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Payment } from "@/types/operations";
import { formatDateTime, inr, titleCase } from "@/utils/format";

export function PaymentsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["payments", { search, status, page }],
    queryFn: () => paymentsApi.list({ search, status, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader title="Payments" description="Every receipt, online payment and refund." />
      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Transaction, reference, invoice…" />
          <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} wrapperClassName="sm:w-48">
            <option value="">All statuses</option>
            {["SUCCEEDED", "PENDING", "FAILED", "PARTIALLY_REFUNDED", "REFUNDED"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </Select>
        </div>
        <DataTable<Payment>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(p) => p.id}
          emptyTitle="No payments yet"
          columns={[
            { key: "when", header: "When", render: (p) => <span className="whitespace-nowrap">{formatDateTime(p.paid_at ?? p.created_at)}</span> },
            { key: "amount", header: "Amount", render: (p) => <span className="font-medium">{inr(p.amount)}</span> },
            { key: "for", header: "For", render: (p) => p.invoice_number ?? p.booking_number ?? "—", hideOnMobile: true },
            { key: "customer", header: "Customer", render: (p) => p.customer_name, hideOnMobile: true },
            { key: "method", header: "Method", render: (p) => titleCase(p.method), hideOnMobile: true },
            { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} /> },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
    </>
  );
}
