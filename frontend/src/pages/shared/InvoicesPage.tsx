import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { invoicesApi } from "@/api/operations";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import type { Invoice } from "@/types/operations";
import { formatDate, inr, titleCase } from "@/utils/format";

const TABS = { all: undefined, due: ["UNPAID", "PARTIALLY_PAID"], paid: ["PAID"] } as const;

export function InvoicesPage({ basePath }: { basePath: string }) {
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const [tab, setTab] = useState<keyof typeof TABS>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["invoices", { tab, search, page }],
    queryFn: () => invoicesApi.list({ payment_status: TABS[tab], search, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader title={isCustomer ? "My invoices" : "Invoices"} description="Generated automatically when a service is completed." />
      <Tabs items={[{ key: "all", label: "All" }, { key: "due", label: "Payment due" }, { key: "paid", label: "Paid" }]} active={tab}
        onChange={(k) => { setTab(k); setPage(1); }} />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Invoice no., customer, booking no…" /></div>
        <DataTable<Invoice>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(i) => i.id}
          emptyTitle="No invoices"
          columns={[
            {
              key: "no", header: "Invoice",
              render: (i) => (
                <Link to={`${basePath}/${i.id}`} className="block">
                  <span className="font-medium text-slate-900 hover:underline">{i.invoice_number}</span>
                  <span className="block text-xs text-slate-500">{formatDate(i.invoice_date)}</span>
                </Link>
              ),
            },
            isCustomer
              ? { key: "agency", header: "Workshop", render: (i: Invoice) => i.organization_name, hideOnMobile: true }
              : { key: "customer", header: "Customer", render: (i: Invoice) => i.customer_name, hideOnMobile: true },
            { key: "total", header: "Total", render: (i) => <span className="font-medium">{inr(i.total)}</span> },
            { key: "due", header: "Balance", render: (i) => inr(i.balance_due), hideOnMobile: true },
            { key: "status", header: "Status", render: (i) => <StatusBadge status={i.status === "VOID" ? "VOID" : i.payment_status} label={i.status === "VOID" ? "Void" : titleCase(i.payment_status)} /> },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
    </>
  );
}
