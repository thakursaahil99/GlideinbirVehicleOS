import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, ClipboardList, FileText, MapPin, Phone, UserCog } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { resourcesApi, staffApi } from "@/api/agency";
import { ApiError } from "@/api/client";
import { bookingsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Alert, Card, PageHeader, Skeleton } from "@/components/ui/Card";
import { Select, Textarea } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import { SlotPicker } from "@/features/booking/SlotPicker";
import { useAuth } from "@/hooks/useAuth";
import type { Booking, Slot } from "@/types/operations";
import { BOOKING_STATUS_LABELS, dayLabel, formatDateTime, inr, timeOnly, titleCase } from "@/utils/format";

const TRANSITIONS: Record<string, { label: string; path: "confirm" | "reject" | "receive-vehicle" | "start" | "complete" | "no-show"; tone: "primary" | "success" | "danger" | "secondary" }> = {
  confirm: { label: "Confirm", path: "confirm", tone: "success" },
  receive_vehicle: { label: "Vehicle received", path: "receive-vehicle", tone: "primary" },
  start: { label: "Start service", path: "start", tone: "primary" },
  complete: { label: "Complete", path: "complete", tone: "success" },
  no_show: { label: "No show", path: "no-show", tone: "secondary" },
  reject: { label: "Reject", path: "reject", tone: "danger" },
};

function AssignModal({ booking, open, onClose }: { booking: Booking; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const staff = useQuery({ queryKey: ["staff", "all-active"], queryFn: () => staffApi.list({ is_active: true, page_size: 100 }), enabled: open });
  const resources = useQuery({ queryKey: ["agency", "resources"], queryFn: () => resourcesApi.list({ page_size: 100 }), enabled: open });
  const [staffId, setStaffId] = useState(booking.assigned_staff?.id ?? "");
  const [resourceId, setResourceId] = useState(booking.assigned_resource?.id ?? "");
  const save = useMutation({
    mutationFn: () => bookingsApi.assign(booking.id, { staff: staffId || undefined, resource: resourceId || undefined }),
    onSuccess: (b) => { queryClient.setQueryData(["bookings", b.id], b); toast.show("Assignment saved.", "success"); onClose(); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not assign.", "error"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Assign technician & resource"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!staffId && !resourceId} onClick={() => save.mutate()}>Save</Button></>}>
      <div className="space-y-4">
        <Select label="Technician / staff" value={staffId} onChange={(e) => setStaffId(e.target.value)}>
          <option value="">— keep current —</option>
          {staff.data?.items.map((m) => <option key={m.user_id} value={m.user_id}>{m.full_name}</option>)}
        </Select>
        <Select label="Resource (bay / equipment)" value={resourceId} onChange={(e) => setResourceId(e.target.value)}>
          <option value="">— keep current —</option>
          {resources.data?.items.filter((r) => r.active).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </Select>
        <p className="text-xs text-slate-500">The server rejects assignments that clash with another booking.</p>
      </div>
    </Modal>
  );
}

function RescheduleModal({ booking, open, onClose }: { booking: Booking; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [slot, setSlot] = useState<Slot | null>(null);
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => bookingsApi.reschedule(booking.id, slot!.start, reason),
    onSuccess: (b) => {
      queryClient.setQueryData(["bookings", b.id], b);
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      toast.show("Booking rescheduled.", "success");
      onClose();
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not reschedule.", "error"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Reschedule booking"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} disabled={!slot} onClick={() => save.mutate()}>Move booking</Button></>}>
      <div className="space-y-4">
        {open && <SlotPicker vendorService={booking.vendor_service} selected={slot?.start} onSelect={setSlot} />}
        {slot && <Alert tone="info">New time: {formatDateTime(slot.start)}</Alert>}
        <Textarea label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  );
}

export function BookingDetailPage({ backTo }: { backTo: string }) {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const area = isCustomer ? "customer" : user?.role === "SUPER_ADMIN" ? "admin" : "agency";
  const toast = useToast();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<null | "cancel" | "reschedule" | "assign" | string>(null);
  const [internalNotes, setInternalNotes] = useState<string | null>(null);

  const booking = useQuery({ queryKey: ["bookings", id], queryFn: () => bookingsApi.get(id) });
  const history = useQuery({ queryKey: ["bookings", id, "history"], queryFn: () => bookingsApi.history(id) });

  const refresh = (b: Booking) => {
    queryClient.setQueryData(["bookings", id], b);
    queryClient.invalidateQueries({ queryKey: ["bookings", id, "history"] });
    queryClient.invalidateQueries({ queryKey: ["bookings"], exact: false });
  };
  const onError = (err: unknown) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error");

  const transition = useMutation({
    mutationFn: ({ path, note }: { path: (typeof TRANSITIONS)[string]["path"]; note: string }) => bookingsApi.transition(id, path, note),
    onSuccess: (b) => { refresh(b); setDialog(null); toast.show(`Booking ${BOOKING_STATUS_LABELS[b.status].toLowerCase()}.`, "success"); },
    onError,
  });
  const cancel = useMutation({
    mutationFn: (reason: string) => bookingsApi.cancel(id, reason),
    onSuccess: (b) => { refresh(b); setDialog(null); toast.show("Booking cancelled.", "success"); },
    onError,
  });
  const saveNotes = useMutation({
    mutationFn: () => bookingsApi.updateNotes(id, { internal_notes: internalNotes ?? "" }),
    onSuccess: (b) => { refresh(b); setInternalNotes(null); toast.show("Notes saved.", "success"); },
    onError,
  });

  if (booking.isLoading) return <Skeleton rows={6} />;
  if (!booking.data) return <Alert tone="danger">Booking not found.</Alert>;
  const b = booking.data;
  const actions = b.allowed_actions;
  const pending = dialog ? TRANSITIONS[dialog] : undefined;

  return (
    <>
      <Link to={backTo} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="h-4 w-4" /> Bookings</Link>
      <PageHeader title={b.service.name} description={`${b.booking_number} · ${dayLabel(b.booking_date)} ${timeOnly(b.start_datetime)}–${timeOnly(b.end_datetime)}`}
        actions={<StatusBadge status={b.status} label={BOOKING_STATUS_LABELS[b.status]} />} />

      {b.status === "WAITING_FOR_APPROVAL" && isCustomer && b.job_card_id && (
        <div className="mb-4"><Alert tone="warning">The workshop needs your approval for additional work. <Link className="font-semibold underline" to={`/customer/job-cards/${b.job_card_id}`}>Review now</Link></Alert></div>
      )}
      {b.status === "CANCELLED" && <div className="mb-4"><Alert tone="danger">Cancelled {formatDateTime(b.cancelled_at)}{b.cancellation_reason && ` — ${b.cancellation_reason}`}</Alert></div>}

      {actions.length > 0 && (
        <div className="stagger mb-6 flex flex-wrap gap-2">
          {actions.filter((a) => TRANSITIONS[a]).map((a) => (
            <Button key={a} variant={TRANSITIONS[a].tone} onClick={() => setDialog(a)}>{TRANSITIONS[a].label}</Button>
          ))}
          {actions.includes("assign") && <Button variant="secondary" onClick={() => setDialog("assign")}><UserCog className="h-4 w-4" /> Assign</Button>}
          {actions.includes("reschedule") && <Button variant="secondary" onClick={() => setDialog("reschedule")}><CalendarClock className="h-4 w-4" /> Reschedule</Button>}
          {actions.includes("cancel") && <Button variant="ghost" onClick={() => setDialog("cancel")}>Cancel booking</Button>}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Details" className="lg:col-span-2">
          <dl className="grid gap-4 text-sm sm:grid-cols-2">
            {[
              ["Vehicle", `${b.vehicle.brand} ${b.vehicle.model} · ${b.vehicle.registration_number}`],
              [isCustomer ? "Workshop" : "Customer", isCustomer ? b.organization.name : `${b.customer.full_name} · ${b.customer.phone}`],
              ["Price", `${inr(b.quoted_price)} + ${Number(b.tax_rate)}% GST`],
              ["Payment", titleCase(b.payment_status)],
              ["Technician", b.assigned_staff?.full_name ?? "Not assigned"],
              ["Resource", b.assigned_resource?.name ?? "—"],
            ].map(([k, v]) => (
              <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-medium text-slate-900">{v}</dd></div>
            ))}
          </dl>
          {b.pickup_requested && <p className="mt-4 flex items-start gap-1.5 text-sm text-slate-600"><MapPin className="mt-0.5 h-4 w-4 shrink-0" /> Pickup: {b.pickup_address}</p>}
          {b.customer_notes && <div className="mt-4 rounded-xl bg-slate-50 p-3 text-sm"><p className="text-xs text-slate-500">Customer notes</p>{b.customer_notes}</div>}
          <div className="mt-4 flex flex-wrap gap-2">
            {b.job_card_id && <Link to={`/${area}/job-cards/${b.job_card_id}`}><Button size="sm" variant="secondary"><ClipboardList className="h-4 w-4" /> Job card</Button></Link>}
            {b.invoice_id && <Link to={`/${area}/invoices/${b.invoice_id}`}><Button size="sm" variant="secondary"><FileText className="h-4 w-4" /> Invoice</Button></Link>}
            {isCustomer && <a href={`tel:${b.organization.phone}`}><Button size="sm" variant="ghost"><Phone className="h-4 w-4" /> Call workshop</Button></a>}
          </div>
        </Card>

        <Card title="History">
          {history.isLoading ? <Skeleton rows={3} /> : (
            <ol className="relative space-y-4 border-l border-slate-200 pl-4">
              {history.data?.status.map((h) => (
                <li key={h.id} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-brand-500 ring-4 ring-brand-100" />
                  <p className="text-sm font-medium text-slate-800">{BOOKING_STATUS_LABELS[h.to_status] ?? h.to_status}</p>
                  <p className="text-xs text-slate-500">{formatDateTime(h.created_at)}{h.changed_by_name && ` · ${h.changed_by_name}`}</p>
                  {h.note && <p className="text-xs text-slate-600">{h.note}</p>}
                </li>
              ))}
              {history.data?.reschedules.map((r) => (
                <li key={r.id} className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-accent-500 ring-4 ring-cyan-100" />
                  <p className="text-sm font-medium text-slate-800">Rescheduled</p>
                  <p className="text-xs text-slate-500">{formatDateTime(r.old_start)} → {formatDateTime(r.new_start)}</p>
                  {r.reason && <p className="text-xs text-slate-600">{r.reason}</p>}
                </li>
              ))}
            </ol>
          )}
        </Card>

        {!isCustomer && (
          <Card title="Internal notes" className="lg:col-span-3">
            <Textarea aria-label="Internal notes" value={internalNotes ?? b.internal_notes ?? ""} onChange={(e) => setInternalNotes(e.target.value)} placeholder="Only your team sees this." />
            {internalNotes !== null && <Button size="sm" className="mt-3" loading={saveNotes.isPending} onClick={() => saveNotes.mutate()}>Save notes</Button>}
          </Card>
        )}
      </div>

      <ConfirmDialog open={Boolean(pending)} title={pending ? `${pending.label}?` : ""} tone={pending?.tone === "danger" ? "danger" : "primary"}
        message={pending?.path === "complete" ? "Completing generates the invoice automatically." : "The customer will be notified."}
        confirmLabel={pending?.label} withReason={pending?.path === "reject"} reasonRequired={false}
        loading={transition.isPending} onCancel={() => setDialog(null)} onConfirm={(note) => pending && transition.mutate({ path: pending.path, note })} />
      <ConfirmDialog open={dialog === "cancel"} title="Cancel this booking?" tone="danger" confirmLabel="Cancel booking"
        message="Bookings are never deleted — it stays in history as cancelled." withReason reasonRequired
        loading={cancel.isPending} onCancel={() => setDialog(null)} onConfirm={(reason) => cancel.mutate(reason)} />
      {dialog === "reschedule" && <RescheduleModal booking={b} open onClose={() => setDialog(null)} />}
      {dialog === "assign" && <AssignModal booking={b} open onClose={() => setDialog(null)} />}
    </>
  );
}
