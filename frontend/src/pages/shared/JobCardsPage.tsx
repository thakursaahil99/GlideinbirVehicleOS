import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { jobCardsApi } from "@/api/operations";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import type { JobCard } from "@/types/operations";
import { formatDateTime, titleCase } from "@/utils/format";

const FILTERS = {
  active: "OPEN,INSPECTION,WORK_IN_PROGRESS,WAITING_APPROVAL",
  done: "COMPLETED,CLOSED",
  all: "",
} as const;

export function JobCardsPage({ basePath }: { basePath: string }) {
  const [tab, setTab] = useState<keyof typeof FILTERS>("active");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["job-cards", { tab, search, page }],
    queryFn: () => jobCardsApi.list({ status: FILTERS[tab] ? FILTERS[tab].split(",") : undefined, search, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader title="Job cards" description="Inspections, work, extra-work approvals and parts for vehicles in the workshop." />
      <Tabs items={[{ key: "active", label: "In workshop" }, { key: "done", label: "Completed" }, { key: "all", label: "All" }]} active={tab}
        onChange={(k) => { setTab(k); setPage(1); }} />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Job no., booking no., reg. no., customer…" /></div>
        <DataTable<JobCard>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(j) => j.id}
          emptyTitle="No job cards"
          columns={[
            {
              key: "no", header: "Job card",
              render: (j) => (
                <Link to={`${basePath}/${j.id}`} className="block">
                  <span className="font-medium text-slate-900 hover:underline">{j.job_card_number}</span>
                  <span className="block text-xs text-slate-500">{j.booking.service}</span>
                </Link>
              ),
            },
            { key: "vehicle", header: "Vehicle", render: (j) => <span className="font-mono text-sm">{j.vehicle.registration_number}</span> },
            { key: "customer", header: "Customer", render: (j) => j.customer.full_name, hideOnMobile: true },
            { key: "tech", header: "Technician", render: (j) => j.booking.assigned_staff ?? "—", hideOnMobile: true },
            { key: "opened", header: "Opened", render: (j) => formatDateTime(j.created_at), hideOnMobile: true },
            { key: "status", header: "Status", render: (j) => <StatusBadge status={j.status} label={titleCase(j.status)} /> },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
    </>
  );
}
