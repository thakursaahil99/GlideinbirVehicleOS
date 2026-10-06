import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { scheduleApi } from "@/api/agency";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DataTable } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import type { Holiday, HolidayKind, SpecialDay } from "@/types/api";
import { formatDate } from "@/utils/format";

function HolidayForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "", kind: "HOLIDAY" as HolidayKind, notes: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => scheduleApi.createHoliday({ ...form, end_date: form.end_date || form.start_date }),
    onSuccess: () => {
      toast.show("Closure added.", "success");
      setForm({ name: "", start_date: "", end_date: "", kind: "HOLIDAY", notes: "" });
      setErrors({});
      onDone();
    },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  return (
    <form className="grid gap-3 sm:grid-cols-5 sm:items-end" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <Input label="Name" value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} wrapperClassName="sm:col-span-2" />
      <Input label="From" type="date" value={form.start_date} error={errors.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
      <Input label="To" type="date" value={form.end_date} error={errors.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
      <Select label="Type" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as HolidayKind })}>
        <option value="HOLIDAY">Holiday</option>
        <option value="EMERGENCY_CLOSURE">Emergency closure</option>
      </Select>
      <div className="sm:col-span-5"><Button type="submit" size="sm" loading={create.isPending}>Add closure</Button></div>
    </form>
  );
}

function SpecialDayForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ date: "", opens_at: "10:00", closes_at: "14:00", note: "" });
  const save = useMutation({
    mutationFn: () => scheduleApi.setSpecialDay(form.date, [{ opens_at: form.opens_at, closes_at: form.closes_at, note: form.note }]),
    onSuccess: () => { toast.show("Special hours saved.", "success"); onDone(); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not save.", "error"),
  });
  return (
    <form className="grid gap-3 sm:grid-cols-5 sm:items-end" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <Input label="Date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
      <Input label="Opens" type="time" value={form.opens_at} onChange={(e) => setForm({ ...form, opens_at: e.target.value })} />
      <Input label="Closes" type="time" value={form.closes_at} onChange={(e) => setForm({ ...form, closes_at: e.target.value })} />
      <Input label="Note" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} wrapperClassName="sm:col-span-2" />
      <div className="sm:col-span-5"><Button type="submit" size="sm" disabled={!form.date} loading={save.isPending}>Save special hours</Button></div>
    </form>
  );
}

export function ClosuresTab({ canEdit }: { canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const holidays = useQuery({ queryKey: ["agency", "holidays"], queryFn: () => scheduleApi.holidays({ upcoming: true, page_size: 100 }) });
  const specials = useQuery({
    queryKey: ["agency", "special-days"],
    queryFn: () => scheduleApi.specialDays({ date_from: new Date().toISOString().slice(0, 10), page_size: 100 }),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["agency"] });

  const removeHoliday = useMutation({
    mutationFn: scheduleApi.deleteHoliday,
    onSuccess: () => { toast.show("Closure removed.", "success"); refresh(); },
  });
  const clearDay = useMutation({
    mutationFn: (date: string) => scheduleApi.setSpecialDay(date, []),
    onSuccess: () => { toast.show("Special hours cleared.", "success"); refresh(); },
  });

  return (
    <div className="space-y-6">
      <Card title="Holidays & emergency closures">
        {canEdit && <div className="mb-5 border-b border-slate-100 pb-5"><HolidayForm onDone={refresh} /></div>}
        <DataTable<Holiday>
          rows={holidays.data?.items}
          loading={holidays.isFetching}
          rowKey={(h) => h.id}
          emptyTitle="No upcoming closures"
          columns={[
            { key: "name", header: "Name", render: (h) => <span className="font-medium text-slate-900">{h.name}</span> },
            { key: "dates", header: "Dates", render: (h) => (h.start_date === h.end_date ? formatDate(h.start_date) : `${formatDate(h.start_date)} → ${formatDate(h.end_date)}`) },
            { key: "kind", header: "Type", render: (h) => <StatusBadge status={h.kind === "HOLIDAY" ? "INACTIVE" : "SUSPENDED"} label={h.kind === "HOLIDAY" ? "Holiday" : "Emergency"} /> },
            {
              key: "del", header: "", className: "text-right",
              render: (h) => canEdit && (
                <button type="button" aria-label="Delete closure" onClick={() => removeHoliday.mutate(h.id)} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-4 w-4" />
                </button>
              ),
            },
          ]}
        />
      </Card>
      <Card title="Special working dates">
        <p className="mb-4 text-xs text-slate-500">Overrides the weekly hours for a single date — e.g. open on a Sunday or close early.</p>
        {canEdit && <div className="mb-5 border-b border-slate-100 pb-5"><SpecialDayForm onDone={refresh} /></div>}
        <DataTable<SpecialDay>
          rows={specials.data?.items}
          loading={specials.isFetching}
          rowKey={(d) => d.id}
          emptyTitle="No special dates"
          columns={[
            { key: "date", header: "Date", render: (d) => formatDate(d.date) },
            { key: "hours", header: "Hours", render: (d) => `${d.opens_at.slice(0, 5)} – ${d.closes_at.slice(0, 5)}` },
            { key: "note", header: "Note", render: (d) => d.note || "—", hideOnMobile: true },
            {
              key: "del", header: "", className: "text-right",
              render: (d) => canEdit && (
                <button type="button" aria-label="Clear special hours" onClick={() => clearDay.mutate(d.date)} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-4 w-4" />
                </button>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
