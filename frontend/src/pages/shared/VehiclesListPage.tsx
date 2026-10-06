import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";

import { vehiclesApi } from "@/api/customers";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/FormField";
import { SearchBar } from "@/components/ui/SearchBar";
import { VehicleFormModal } from "@/features/vehicles/VehicleFormModal";
import type { Vehicle } from "@/types/api";
import { VEHICLE_TYPE_LABELS, expiresSoon, formatDate } from "@/utils/format";

export function VehiclesListPage() {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Vehicle | null>(null);
  const query = useQuery({
    queryKey: ["vehicles", "list", { search, type, page }],
    queryFn: () => vehiclesApi.list({ search, vehicle_type: type, page }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader title="Vehicles" description="Vehicles of customers you can see." />
      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Registration, VIN, brand, owner…" />
          <Select aria-label="Vehicle type" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} wrapperClassName="sm:w-48">
            <option value="">All types</option>
            {Object.entries(VEHICLE_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        <DataTable<Vehicle>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(v) => v.id}
          emptyTitle="No vehicles found"
          columns={[
            { key: "reg", header: "Registration", render: (v) => <span className="font-mono font-medium text-slate-900">{v.registration_number}</span> },
            { key: "vehicle", header: "Vehicle", render: (v) => `${v.brand} ${v.model}` },
            { key: "type", header: "Type", render: (v) => VEHICLE_TYPE_LABELS[v.vehicle_type], hideOnMobile: true },
            { key: "owner", header: "Owner", render: (v) => v.customer_name, hideOnMobile: true },
            {
              key: "insurance", header: "Insurance", hideOnMobile: true,
              render: (v) => <span className={expiresSoon(v.insurance_expiry) ? "text-amber-700" : ""}>{formatDate(v.insurance_expiry)}</span>,
            },
            {
              key: "actions", header: "", className: "text-right",
              render: (v) => v.can_edit && <Button size="sm" variant="secondary" onClick={() => setEditing(v)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>,
            },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
      <VehicleFormModal open={Boolean(editing)} vehicle={editing} onClose={() => setEditing(null)} />
    </>
  );
}
