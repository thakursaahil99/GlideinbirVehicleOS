import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { catalogApi } from "@/api/services";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Checkbox, Toggle } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import type { CatalogService, VehicleType } from "@/types/api";
import { CATEGORY_LABELS, VEHICLE_TYPE_LABELS, formatDuration, inr } from "@/utils/format";

const EMPTY: Partial<CatalogService> = {
  name: "", category: "MAINTENANCE", description: "", supported_vehicle_types: ["CAR"], default_duration: 60,
  base_price: "0", tax: "18.00", active: true,
};

function ServiceModal({ service, open, onClose }: { service: CatalogService | null; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<CatalogService>>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => { if (open) { setForm(service ?? EMPTY); setErrors({}); } }, [open, service]);

  const save = useMutation({
    mutationFn: () => {
      const { id: _id, slug: _slug, ...payload } = form;
      return service ? catalogApi.update(service.id, payload) : catalogApi.create(payload);
    },
    onSuccess: () => { toast.show("Catalog updated.", "success"); queryClient.invalidateQueries({ queryKey: ["catalog"] }); onClose(); },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  const types = form.supported_vehicle_types ?? [];

  return (
    <Modal open={open} onClose={onClose} title={service ? `Edit ${service.name}` : "New catalog service"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Name" value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} wrapperClassName="sm:col-span-2" />
        <Select label="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as CatalogService["category"] })}>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Input label="Default duration (min)" type="number" value={form.default_duration} error={errors.default_duration}
          onChange={(e) => setForm({ ...form, default_duration: Number(e.target.value) })} />
        <Input label="Base price (₹)" type="number" step="0.01" value={form.base_price} error={errors.base_price}
          onChange={(e) => setForm({ ...form, base_price: e.target.value })} />
        <Input label="GST (%)" type="number" step="0.01" value={form.tax} error={errors.tax} onChange={(e) => setForm({ ...form, tax: e.target.value })} />
        <fieldset className="sm:col-span-2">
          <legend className="mb-2 text-sm font-medium text-slate-700">Vehicle types</legend>
          <div className="flex flex-wrap gap-4">
            {(Object.keys(VEHICLE_TYPE_LABELS) as VehicleType[]).map((t) => (
              <Checkbox key={t} label={VEHICLE_TYPE_LABELS[t]} checked={types.includes(t)}
                onChange={(on) => setForm({ ...form, supported_vehicle_types: on ? [...types, t] : types.filter((x) => x !== t) })} />
            ))}
          </div>
          {errors.supported_vehicle_types && <p className="mt-1 text-xs text-rose-600">{errors.supported_vehicle_types}</p>}
        </fieldset>
        <Textarea label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} wrapperClassName="sm:col-span-2" />
        <div className="sm:col-span-2"><Toggle label="Active" description="Inactive services can't be offered or booked." checked={Boolean(form.active)} onChange={(v) => setForm({ ...form, active: v })} /></div>
      </div>
    </Modal>
  );
}

export function AdminServicesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<CatalogService | null | undefined>(undefined);
  const query = useQuery({
    queryKey: ["catalog", { search, page }],
    queryFn: () => catalogApi.list({ search, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <PageHeader title="Service catalog" description="Global services agencies can offer with their own pricing."
        actions={<Button onClick={() => setEditing(null)}><Plus className="h-4 w-4" /> New service</Button>} />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} /></div>
        <DataTable<CatalogService>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(s) => s.id}
          columns={[
            { key: "name", header: "Service", render: (s) => <button type="button" className="font-medium text-slate-900 hover:underline" onClick={() => setEditing(s)}>{s.name}</button> },
            { key: "cat", header: "Category", render: (s) => CATEGORY_LABELS[s.category], hideOnMobile: true },
            { key: "types", header: "Vehicles", render: (s) => s.supported_vehicle_types.map((t) => VEHICLE_TYPE_LABELS[t]).join(", "), hideOnMobile: true },
            { key: "duration", header: "Duration", render: (s) => formatDuration(s.default_duration), hideOnMobile: true },
            { key: "price", header: "Base price", render: (s) => inr(s.base_price) },
            { key: "active", header: "Status", render: (s) => <StatusBadge status={s.active ? "ACTIVE" : "INACTIVE"} /> },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
      <ServiceModal open={editing !== undefined} service={editing ?? null} onClose={() => setEditing(undefined)} />
    </>
  );
}
