import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bike, Car, FileText, Pencil, Plus, Zap } from "lucide-react";
import { useState } from "react";

import { vehiclesApi } from "@/api/customers";
import { Button } from "@/components/ui/Button";
import { EmptyState, PageHeader, Spinner } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import { VehicleDocumentsModal } from "@/features/vehicles/VehicleDocumentsModal";
import { VehicleFormModal } from "@/features/vehicles/VehicleFormModal";
import type { Vehicle } from "@/types/api";
import { FUEL_LABELS, VEHICLE_TYPE_LABELS, expiresSoon, formatDate } from "@/utils/format";

export const vehicleIcon = (type: string) => (type === "BIKE" || type === "SCOOTER" ? Bike : type === "EV" ? Zap : Car);

function Expiry({ label, date }: { label: string; date: string | null }) {
  if (!date) return null;
  const soon = expiresSoon(date);
  return (
    <span className={soon ? "inline-flex items-center gap-1 text-amber-700" : "text-slate-500"}>
      {soon && <AlertTriangle className="h-3 w-3" />} {label} {formatDate(date)}
    </span>
  );
}

export function CustomerVehiclesPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["vehicles", "mine"], queryFn: () => vehiclesApi.list({ page_size: 100 }) });
  const [editing, setEditing] = useState<Vehicle | null | undefined>(undefined);
  const [docsFor, setDocsFor] = useState<Vehicle | null>(null);
  const [archiving, setArchiving] = useState<Vehicle | null>(null);

  const archive = useMutation({
    mutationFn: (v: Vehicle) => vehiclesApi.archive(v.id),
    onSuccess: () => {
      toast.show("Vehicle archived. Its service history is kept.", "success");
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      setArchiving(null);
    },
  });

  return (
    <>
      <PageHeader title="My vehicles" description="Cars, bikes, scooters and EVs you can book services for."
        actions={<Button onClick={() => setEditing(null)}><Plus className="h-4 w-4" /> Add vehicle</Button>} />
      {query.isLoading ? <Spinner /> : query.data?.items.length === 0 ? (
        <div className="rounded-xl bg-white ring-1 ring-slate-200">
          <EmptyState title="No vehicles yet" description="Add your first vehicle to start booking services." />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {query.data?.items.map((v) => {
            const Icon = vehicleIcon(v.vehicle_type);
            return (
              <article key={v.id} className="flex flex-col rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
                <div className="flex items-start gap-3">
                  <div className="rounded-lg bg-brand-50 p-2 text-brand-600"><Icon className="h-5 w-5" /></div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate font-semibold text-slate-900">{v.brand} {v.model} {v.variant}</h3>
                    <p className="font-mono text-sm tracking-wide text-slate-600">{v.registration_number}</p>
                  </div>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-1 text-xs text-slate-600">
                  <div>{VEHICLE_TYPE_LABELS[v.vehicle_type]} · {FUEL_LABELS[v.fuel_type]}</div>
                  <div>{v.manufacturing_year ?? "—"} · {v.odometer ? `${v.odometer.toLocaleString("en-IN")} km` : "—"}</div>
                </dl>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                  <Expiry label="Insurance" date={v.insurance_expiry} />
                  <Expiry label="PUC" date={v.pollution_expiry} />
                </div>
                <div className="mt-4 flex gap-2 border-t border-slate-100 pt-3">
                  <Button size="sm" variant="secondary" onClick={() => setEditing(v)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                  <Button size="sm" variant="secondary" onClick={() => setDocsFor(v)}><FileText className="h-3.5 w-3.5" /> Documents</Button>
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setArchiving(v)}>Archive</Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      <VehicleFormModal open={editing !== undefined} vehicle={editing ?? null} onClose={() => setEditing(undefined)} />
      <VehicleDocumentsModal vehicle={docsFor} onClose={() => setDocsFor(null)} />
      <ConfirmDialog open={Boolean(archiving)} title="Archive vehicle?" tone="danger" confirmLabel="Archive"
        message="It will no longer appear in booking, but its service history is kept." loading={archive.isPending}
        onCancel={() => setArchiving(null)} onConfirm={() => archiving && archive.mutate(archiving)} />
    </>
  );
}
