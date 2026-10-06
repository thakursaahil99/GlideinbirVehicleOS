import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { agencySettingsApi } from "@/api/agency";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, Spinner } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { Toggle } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import type { AgencySettings } from "@/types/api";

type NumberKey = "buffer_minutes" | "booking_lead_time_minutes" | "max_advance_days" | "cancellation_cutoff_hours";
const NUMBER_FIELDS: { key: NumberKey; label: string; hint: string }[] = [
  { key: "buffer_minutes", label: "Buffer between bookings (min)", hint: "Kept free after every booking for clean-up." },
  { key: "booking_lead_time_minutes", label: "Minimum notice (min)", hint: "Earliest bookable slot from now." },
  { key: "max_advance_days", label: "Book up to (days ahead)", hint: "1–365." },
  { key: "cancellation_cutoff_hours", label: "Cancellation cut-off (hours)", hint: "Customers can't cancel or reschedule closer than this." },
];

export function BookingRulesTab({ canEdit }: { canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["agency", "settings"], queryFn: agencySettingsApi.get });
  const [form, setForm] = useState<AgencySettings | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => { if (query.data) setForm(query.data); }, [query.data]);

  const save = useMutation({
    mutationFn: () => {
      const { updated_at: _u, ...payload } = form!;
      return agencySettingsApi.update(payload);
    },
    onSuccess: (data) => { queryClient.setQueryData(["agency", "settings"], data); setErrors({}); toast.show("Booking rules saved.", "success"); },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });

  if (!form) return <Spinner />;

  return (
    <Card title="Booking rules" actions={canEdit && <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>Save rules</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        {NUMBER_FIELDS.map((f) => (
          <Input key={f.key} type="number" min={0} label={f.label} hint={f.hint} disabled={!canEdit} error={errors[f.key]}
            value={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: Number(e.target.value) })} />
        ))}
        <Input type="number" min={5} label="Slot step (min)" hint="Leave empty to step by service duration + buffer." disabled={!canEdit}
          error={errors.slot_interval_minutes} value={form.slot_interval_minutes ?? ""}
          onChange={(e) => setForm({ ...form, slot_interval_minutes: e.target.value ? Number(e.target.value) : null })} />
      </div>
      <div className="mt-6 space-y-4 border-t border-slate-100 pt-5">
        <Toggle label="Auto-confirm bookings" description="New bookings skip the PENDING review step." disabled={!canEdit}
          checked={form.auto_confirm_bookings} onChange={(v) => setForm({ ...form, auto_confirm_bookings: v })} />
        <Toggle label="Additional work needs customer approval" description="Extra work found during service waits for the customer's OK." disabled={!canEdit}
          checked={form.additional_work_requires_approval} onChange={(v) => setForm({ ...form, additional_work_requires_approval: v })} />
        <Toggle label="Require online payment at booking" description="Customers pay through the payment gateway (mock in development)." disabled={!canEdit}
          checked={form.require_online_payment} onChange={(v) => setForm({ ...form, require_online_payment: v })} />
      </div>
    </Card>
  );
}
