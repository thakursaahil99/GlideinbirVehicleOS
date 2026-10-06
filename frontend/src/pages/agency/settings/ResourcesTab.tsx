import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { resourcesApi, staffApi } from "@/api/agency";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import type { ResourceType, ServiceResource } from "@/types/api";

export const RESOURCE_LABELS: Record<ResourceType, string> = {
  BAY: "Service bay",
  TECHNICIAN: "Technician",
  EQUIPMENT: "Equipment",
  OTHER: "Other",
};

export function ResourcesTab({ canEdit }: { canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: ["agency", "resources"], queryFn: () => resourcesApi.list({ page_size: 100 }) });
  const staff = useQuery({ queryKey: ["staff", "all-active"], queryFn: () => staffApi.list({ is_active: true, page_size: 100 }), enabled: canEdit });
  const [form, setForm] = useState({ name: "", resource_type: "BAY" as ResourceType, staff: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["agency", "resources"] });
  const onError = (err: unknown) => {
    if (err instanceof ApiError) {
      setErrors(err.fieldErrors());
      toast.show(err.message, "error");
    }
  };

  const create = useMutation({
    mutationFn: () => resourcesApi.create({ name: form.name, resource_type: form.resource_type, staff: form.staff || null }),
    onSuccess: () => { toast.show("Resource added.", "success"); setForm({ name: "", resource_type: "BAY", staff: "" }); setErrors({}); refresh(); },
    onError,
  });
  const toggle = useMutation({
    mutationFn: (r: ServiceResource) => resourcesApi.update(r.id, { active: !r.active }),
    onSuccess: refresh,
    onError,
  });

  return (
    <Card title="Bookable resources">
      <p className="mb-4 text-xs text-slate-500">
        Bays, technicians and equipment are reserved by bookings. The availability engine never double-books a resource.
      </p>
      {canEdit && (
        <form className="mb-5 grid gap-3 border-b border-slate-100 pb-5 sm:grid-cols-4 sm:items-end" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Input label="Name" placeholder="Bay 1" value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="Type" value={form.resource_type} onChange={(e) => setForm({ ...form, resource_type: e.target.value as ResourceType, staff: "" })}>
            {(Object.keys(RESOURCE_LABELS) as ResourceType[]).map((t) => <option key={t} value={t}>{RESOURCE_LABELS[t]}</option>)}
          </Select>
          <Select label="Staff (technicians)" value={form.staff} error={errors.staff} disabled={form.resource_type !== "TECHNICIAN"} onChange={(e) => setForm({ ...form, staff: e.target.value })}>
            <option value="">—</option>
            {staff.data?.items.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
          </Select>
          <Button type="submit" loading={create.isPending} disabled={!form.name}>Add resource</Button>
        </form>
      )}
      <DataTable<ServiceResource>
        rows={list.data?.items}
        loading={list.isFetching}
        rowKey={(r) => r.id}
        emptyTitle="No resources yet"
        emptyDescription="Add bays or technicians so bookings can reserve them."
        columns={[
          { key: "name", header: "Name", render: (r) => <span className="font-medium text-slate-900">{r.name}</span> },
          { key: "type", header: "Type", render: (r) => RESOURCE_LABELS[r.resource_type] },
          { key: "staff", header: "Staff", render: (r) => r.staff_name ?? "—", hideOnMobile: true },
          { key: "status", header: "Status", render: (r) => <StatusBadge status={r.active ? "ACTIVE" : "INACTIVE"} /> },
          {
            key: "actions", header: "", className: "text-right",
            render: (r) => canEdit && (
              <Button size="sm" variant="secondary" onClick={() => toggle.mutate(r)}>{r.active ? "Deactivate" : "Activate"}</Button>
            ),
          },
        ]}
      />
    </Card>
  );
}
