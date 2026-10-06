import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { catalogApi, offeringsApi } from "@/api/services";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { Input, Select, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Toggle } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { VendorServiceOffering } from "@/types/api";
import { CATEGORY_LABELS, formatDuration, inr } from "@/utils/format";

import { RESOURCE_LABELS } from "./settings/ResourcesTab";

type Form = {
  service: string;
  custom_price: string;
  custom_duration: string;
  capacity: string;
  required_resource_type: string;
  pickup_available: boolean;
  drop_available: boolean;
  online_booking_enabled: boolean;
  active: boolean;
  description: string;
};

const blank: Form = {
  service: "", custom_price: "", custom_duration: "", capacity: "1", required_resource_type: "", pickup_available: false,
  drop_available: false, online_booking_enabled: true, active: true, description: "",
};

function OfferingModal({ offering, open, onClose, offeredIds }: { offering: VendorServiceOffering | null; open: boolean; onClose: () => void; offeredIds: Set<string> }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const catalog = useQuery({ queryKey: ["catalog", "all"], queryFn: () => catalogApi.list({ page_size: 100 }), enabled: open });
  const [form, setForm] = useState<Form>(blank);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(offering ? {
      service: offering.service, custom_price: offering.custom_price ?? "", custom_duration: offering.custom_duration ? String(offering.custom_duration) : "",
      capacity: String(offering.capacity), required_resource_type: offering.required_resource_type, pickup_available: offering.pickup_available,
      drop_available: offering.drop_available, online_booking_enabled: offering.online_booking_enabled, active: offering.active, description: offering.description,
    } : blank);
  }, [open, offering]);

  const selected = catalog.data?.items.find((s) => s.id === form.service) ?? offering?.service_detail;

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        custom_price: form.custom_price === "" ? null : form.custom_price,
        custom_duration: form.custom_duration === "" ? null : Number(form.custom_duration),
        capacity: Number(form.capacity),
      } as unknown as Partial<VendorServiceOffering>;
      return offering ? offeringsApi.update(offering.id, payload) : offeringsApi.create(payload);
    },
    onSuccess: () => { toast.show("Service saved.", "success"); queryClient.invalidateQueries({ queryKey: ["offerings"] }); onClose(); },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });

  return (
    <Modal open={open} onClose={onClose} title={offering ? `Edit ${offering.service_detail.name}` : "Offer a service"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!form.service} onClick={() => save.mutate()}>Save</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Catalog service" value={form.service} disabled={Boolean(offering)} error={errors.service}
          onChange={(e) => setForm({ ...form, service: e.target.value })} wrapperClassName="sm:col-span-2">
          <option value="">Choose…</option>
          {catalog.data?.items.filter((s) => offering || !offeredIds.has(s.id)).map((s) => (
            <option key={s.id} value={s.id}>{s.name} — {CATEGORY_LABELS[s.category]}</option>
          ))}
          {offering && <option value={offering.service}>{offering.service_detail.name}</option>}
        </Select>
        <Input label="Your price (₹)" type="number" step="0.01" value={form.custom_price} error={errors.custom_price}
          placeholder={selected ? `Default ${selected.base_price}` : ""} onChange={(e) => setForm({ ...form, custom_price: e.target.value })} />
        <Input label="Your duration (min)" type="number" value={form.custom_duration} error={errors.custom_duration}
          placeholder={selected ? `Default ${selected.default_duration}` : ""} onChange={(e) => setForm({ ...form, custom_duration: e.target.value })} />
        <Input label="Parallel capacity" type="number" min={1} value={form.capacity} error={errors.capacity}
          hint="Bookings that can run in the same slot." onChange={(e) => setForm({ ...form, capacity: e.target.value })} />
        <Select label="Reserves a resource" value={form.required_resource_type} error={errors.required_resource_type}
          onChange={(e) => setForm({ ...form, required_resource_type: e.target.value })}>
          <option value="">None</option>
          {Object.entries(RESOURCE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Textarea label="Description for customers" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} wrapperClassName="sm:col-span-2" />
        <div className="space-y-3 sm:col-span-2">
          <Toggle label="Active" checked={form.active} onChange={(v) => setForm({ ...form, active: v })} />
          <Toggle label="Online booking" description="Customers can book this service in the app." checked={form.online_booking_enabled} onChange={(v) => setForm({ ...form, online_booking_enabled: v })} />
          <Toggle label="Pickup available" checked={form.pickup_available} onChange={(v) => setForm({ ...form, pickup_available: v })} />
          <Toggle label="Drop available" checked={form.drop_available} onChange={(v) => setForm({ ...form, drop_available: v })} />
        </div>
      </div>
    </Modal>
  );
}

export function AgencyServicesPage() {
  const { user } = useAuth();
  const canManage = Boolean(user?.permissions.includes("SERVICE_MANAGE"));
  const [editing, setEditing] = useState<VendorServiceOffering | null | undefined>(undefined);
  const query = useQuery({ queryKey: ["offerings"], queryFn: () => offeringsApi.list({ page_size: 100 }) });
  const offeredIds = useMemo(() => new Set(query.data?.items.map((o) => o.service)), [query.data]);

  return (
    <>
      <PageHeader title="Services & pricing" description="What you offer, at what price, duration and capacity."
        actions={canManage && <Button onClick={() => setEditing(null)}><Plus className="h-4 w-4" /> Offer service</Button>} />
      <Card>
        <DataTable<VendorServiceOffering>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(o) => o.id}
          emptyTitle="You don't offer any services yet"
          emptyDescription="Pick services from the platform catalog and set your own prices."
          columns={[
            {
              key: "name", header: "Service",
              render: (o) => (
                <button type="button" disabled={!canManage} className="text-left" onClick={() => setEditing(o)}>
                  <span className="font-medium text-slate-900 hover:underline">{o.service_detail.name}</span>
                  <span className="block text-xs text-slate-500">{CATEGORY_LABELS[o.service_detail.category]}</span>
                </button>
              ),
            },
            { key: "price", header: "Price", render: (o) => <span>{inr(o.price)} <span className="text-xs text-slate-400">+{Number(o.tax_rate)}% GST</span></span> },
            { key: "duration", header: "Duration", render: (o) => formatDuration(o.duration), hideOnMobile: true },
            { key: "capacity", header: "Capacity", render: (o) => o.capacity, hideOnMobile: true },
            { key: "resource", header: "Resource", render: (o) => (o.required_resource_type ? RESOURCE_LABELS[o.required_resource_type] : "—"), hideOnMobile: true },
            {
              key: "status", header: "Status",
              render: (o) => <StatusBadge status={o.active && o.online_booking_enabled ? "ACTIVE" : "INACTIVE"} label={!o.active ? "Inactive" : o.online_booking_enabled ? "Bookable" : "Offline only"} />,
            },
          ]}
        />
      </Card>
      <OfferingModal open={editing !== undefined} offering={editing ?? null} onClose={() => setEditing(undefined)} offeredIds={offeredIds} />
    </>
  );
}
