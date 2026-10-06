import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Plus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { customersApi } from "@/api/customers";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Alert, Card, EmptyState, PageHeader, Spinner } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import { VehicleFormModal } from "@/features/vehicles/VehicleFormModal";
import { useAuth } from "@/hooks/useAuth";
import type { Customer } from "@/types/api";
import { VEHICLE_TYPE_LABELS, formatDateTime } from "@/utils/format";

/** Extra panels (bookings, invoices, timeline) are injected by later phases via `children`. */
export function CustomerDetailPage({ backTo, children }: { backTo: string; children?: ReactNode }) {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const isAgency = Boolean(user?.organization);
  const [note, setNote] = useState("");
  const [addingVehicle, setAddingVehicle] = useState(false);
  const [editing, setEditing] = useState(false);

  const customer = useQuery({ queryKey: ["customers", id], queryFn: () => customersApi.get(id) });
  const notes = useQuery({ queryKey: ["customers", id, "notes"], queryFn: () => customersApi.notes(id), enabled: isAgency });
  const addNote = useMutation({
    mutationFn: () => customersApi.addNote(id, note),
    onSuccess: () => { setNote(""); queryClient.invalidateQueries({ queryKey: ["customers", id, "notes"] }); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not save note.", "error"),
  });

  if (customer.isLoading) return <Spinner />;
  if (customer.isError || !customer.data) return <Alert tone="danger">Customer not found.</Alert>;
  const c = customer.data;
  const canAddVehicle = isAgency && user!.permissions.includes("VEHICLE_CREATE");
  const canWriteNotes = isAgency && user!.permissions.includes("CUSTOMER_UPDATE");
  const canEdit = c.can_edit && (user?.role === "SUPER_ADMIN" || user!.permissions.includes("CUSTOMER_UPDATE"));

  return (
    <>
      <Link to={backTo} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft className="h-4 w-4" /> Customers
      </Link>
      <PageHeader title={c.full_name} description={c.has_account ? "Self-registered app user" : "Walk-in customer managed by your agency"} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Contact" className="lg:col-span-1"
          actions={canEdit && <Button size="sm" variant="secondary" onClick={() => setEditing(true)}><Pencil className="h-4 w-4" /> Edit</Button>}>
          <dl className="space-y-3 text-sm">
            {[["Phone", c.phone], ["E-mail", c.email], ["Address", [c.address, c.city, c.state, c.pincode].filter(Boolean).join(", ")]].map(([k, v]) => (
              <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-medium text-slate-800">{v || "—"}</dd></div>
            ))}
          </dl>
          {!c.can_edit && isAgency && <p className="mt-4 text-xs text-slate-500">This customer manages their own profile.</p>}
        </Card>

        <Card title="Vehicles" className="lg:col-span-2"
          actions={canAddVehicle && c.can_edit && <Button size="sm" onClick={() => setAddingVehicle(true)}><Plus className="h-4 w-4" /> Add vehicle</Button>}>
          {c.vehicles?.length ? (
            <ul className="divide-y divide-slate-100">
              {c.vehicles.map((v) => (
                <li key={v.id} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="font-medium text-slate-900">{v.brand} {v.model}</span>
                  <span className="font-mono text-slate-600">{v.registration_number}</span>
                  <span className="hidden text-slate-500 sm:inline">{VEHICLE_TYPE_LABELS[v.vehicle_type]}</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No vehicles" />}
        </Card>

        {children}

        {isAgency && (
          <Card title="Internal notes" className="lg:col-span-3">
            <p className="mb-3 text-xs text-slate-500">Visible only to your agency — never to the customer or other agencies.</p>
            {canWriteNotes && (
              <form className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); if (note.trim()) addNote.mutate(); }}>
                <Textarea aria-label="New note" value={note} onChange={(e) => setNote(e.target.value)} wrapperClassName="flex-1" placeholder="e.g. Prefers morning drop-off" />
                <Button type="submit" loading={addNote.isPending} disabled={!note.trim()}>Add note</Button>
              </form>
            )}
            <ul className="space-y-3">
              {notes.data?.items.length === 0 && <li className="text-sm text-slate-500">No notes yet.</li>}
              {notes.data?.items.map((n) => (
                <li key={n.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <p className="whitespace-pre-wrap text-slate-800">{n.body}</p>
                  <p className="mt-1 text-xs text-slate-500">{n.author_name ?? "—"} · {formatDateTime(n.created_at)}</p>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
      <CustomerEditModal customer={editing ? c : null} onClose={() => setEditing(false)} />
      <VehicleFormModal open={addingVehicle} vehicle={null} customerId={c.id} onClose={() => setAddingVehicle(false)} />
    </>
  );
}

const CUSTOMER_FIELDS: [keyof Customer, string][] = [
  ["full_name", "Full name"], ["phone", "Phone"], ["email", "E-mail"], ["address", "Address"],
  ["city", "City"], ["state", "State"], ["country", "Country"], ["pincode", "Pincode"],
];

function CustomerEditModal({ customer, onClose }: { customer: Customer | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!customer) return;
    setErrors({});
    setForm(Object.fromEntries(CUSTOMER_FIELDS.map(([k]) => [k, String(customer[k] ?? "")])));
  }, [customer]);
  const save = useMutation({
    mutationFn: () => customersApi.update(customer!.id, form as Partial<Customer>),
    onSuccess: () => {
      toast.show("Customer updated.", "success");
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });
  return (
    <Modal open={Boolean(customer)} title="Edit customer" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save changes</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        {CUSTOMER_FIELDS.map(([k, label]) => (
          <Input key={k} label={label} value={form[k] ?? ""} error={errors[k]} wrapperClassName={k === "full_name" || k === "address" ? "sm:col-span-2" : undefined}
            onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} />
        ))}
      </div>
    </Modal>
  );
}
