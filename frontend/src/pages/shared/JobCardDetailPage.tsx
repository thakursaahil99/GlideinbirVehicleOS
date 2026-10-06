import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Camera, CheckCircle2, Package, Play, Plus, Undo2, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "@/api/client";
import { inventoryApi, jobCardsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Alert, Card, PageHeader, Skeleton } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { JobCard } from "@/types/operations";
import { cn, formatDateTime, inr, titleCase } from "@/utils/format";

const AREAS = ["EXTERIOR", "INTERIOR", "TYRES", "BRAKES", "LIGHTS", "ENGINE", "BATTERY", "AC", "FLUIDS", "OTHER"];
const RESULTS: { key: string; label: string; tone: string }[] = [
  { key: "OK", label: "OK", tone: "bg-emerald-600 text-white" },
  { key: "ATTENTION", label: "Attention", tone: "bg-amber-500 text-white" },
  { key: "REPLACE", label: "Replace", tone: "bg-rose-600 text-white" },
  { key: "NOT_CHECKED", label: "—", tone: "bg-slate-400 text-white" },
];
const EDITABLE = ["OPEN", "INSPECTION", "WORK_IN_PROGRESS", "WAITING_APPROVAL"];

function InspectionPanel({ job, canEdit }: { job: JobCard; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<"BEFORE" | "AFTER">("BEFORE");
  const [draft, setDraft] = useState<Record<string, { result: string; notes: string }>>({});
  useEffect(() => {
    const next: Record<string, { result: string; notes: string }> = {};
    for (const a of AREAS) {
      const item = job.inspection_items?.find((i) => i.area === a && i.stage === stage);
      next[a] = { result: item?.result ?? "NOT_CHECKED", notes: item?.notes ?? "" };
    }
    setDraft(next);
  }, [job, stage]);
  const save = useMutation({
    mutationFn: () => jobCardsApi.saveInspection(job.id, AREAS.map((area) => ({ area, stage, ...draft[area] }))),
    onSuccess: (j) => { queryClient.setQueryData(["job-cards", job.id], j); toast.show("Inspection saved.", "success"); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not save.", "error"),
  });
  return (
    <Card title="Inspection checklist" actions={canEdit && <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>Save</Button>}>
      <Tabs items={[{ key: "BEFORE", label: "Before service" }, { key: "AFTER", label: "After service" }]} active={stage} onChange={setStage} />
      <ul className="divide-y divide-slate-100">
        {AREAS.map((area) => (
          <li key={area} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
            <span className="w-28 shrink-0 text-sm font-medium text-slate-800">{titleCase(area)}</span>
            <div className="flex flex-wrap gap-1.5">
              {RESULTS.map((r) => (
                <button key={r.key} type="button" disabled={!canEdit}
                  onClick={() => setDraft({ ...draft, [area]: { ...draft[area], result: r.key } })}
                  className={cn("rounded-lg px-3 py-1.5 text-xs font-medium ring-1 ring-slate-200 transition",
                    draft[area]?.result === r.key ? r.tone : "bg-white text-slate-600 hover:bg-slate-50")}>
                  {r.label}
                </button>
              ))}
            </div>
            <input aria-label={`${area} notes`} disabled={!canEdit} value={draft[area]?.notes ?? ""} placeholder="Notes"
              onChange={(e) => setDraft({ ...draft, [area]: { ...draft[area], notes: e.target.value } })}
              className="min-w-0 flex-1 rounded-xl border-0 px-3 py-2 text-base ring-1 ring-slate-200 focus:ring-2 focus:ring-brand-500 sm:text-sm" />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PartsPanel({ job, canEdit }: { job: JobCard; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [part, setPart] = useState("");
  const [qty, setQty] = useState("1");
  const parts = useQuery({ queryKey: ["parts", "active"], queryFn: () => inventoryApi.list({ active: true, page_size: 100 }), enabled: open });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["job-cards", job.id] });
  const use = useMutation({
    mutationFn: () => jobCardsApi.usePart(job.id, part, qty),
    onSuccess: () => { refresh(); setOpen(false); setPart(""); setQty("1"); toast.show("Part added and stock reduced.", "success"); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not add part.", "error"),
  });
  const ret = useMutation({
    mutationFn: ({ usageId, quantity }: { usageId: string; quantity: string }) => jobCardsApi.returnPart(job.id, usageId, quantity),
    onSuccess: () => { refresh(); toast.show("Returned to stock.", "success"); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not return.", "error"),
  });
  return (
    <Card title={<span className="flex items-center gap-2"><Package className="h-4 w-4" /> Parts used</span>}
      actions={canEdit && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Add part</Button>}>
      {job.parts_used?.length ? (
        <ul className="divide-y divide-slate-100 text-sm">
          {job.parts_used.map((p) => (
            <li key={p.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-900">{p.part_name}</p>
                <p className="text-xs text-slate-500">{Number(p.net_quantity)} × {inr(p.unit_price)}{Number(p.returned_quantity) > 0 && ` · ${Number(p.returned_quantity)} returned`}</p>
              </div>
              <span className="font-medium">{inr(Number(p.net_quantity) * Number(p.unit_price))}</span>
              {canEdit && Number(p.net_quantity) > 0 && (
                <button type="button" aria-label="Return one" className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  onClick={() => ret.mutate({ usageId: p.id, quantity: "1" })}><Undo2 className="h-4 w-4" /></button>
              )}
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No parts used yet.</p>}
      <Modal open={open} onClose={() => setOpen(false)} title="Use a part"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={use.isPending} disabled={!part} onClick={() => use.mutate()}>Add</Button></>}>
        <div className="space-y-4">
          <Select label="Part" value={part} onChange={(e) => setPart(e.target.value)}>
            <option value="">Choose…</option>
            {parts.data?.items.map((p) => <option key={p.id} value={p.id} disabled={Number(p.stock_quantity) <= 0}>{p.name} · {Number(p.stock_quantity)} in stock</option>)}
          </Select>
          <Input label="Quantity" type="number" inputMode="decimal" min="0.01" step="0.01" value={qty} onChange={(e) => setQty(e.target.value)} />
        </div>
      </Modal>
    </Card>
  );
}

function AdditionalWorkPanel({ job, isCustomer, canEdit }: { job: JobCard; isCustomer: boolean; canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("");
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["job-cards", job.id] });
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
  };
  const onError = (err: unknown) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error");
  const request = useMutation({
    mutationFn: () => jobCardsApi.requestWork(job.id, description, cost),
    onSuccess: (w) => { refresh(); setOpen(false); setDescription(""); setCost(""); toast.show(w.status === "PENDING" ? "Sent to the customer for approval." : "Added (auto-approved).", "success"); },
    onError,
  });
  const respond = useMutation({
    mutationFn: ({ workId, approve }: { workId: string; approve: boolean }) => jobCardsApi.respondWork(job.id, workId, approve),
    onSuccess: (w) => { refresh(); toast.show(w.status === "APPROVED" ? "Approved — work will continue." : "Declined.", "success"); },
    onError,
  });
  const withdraw = useMutation({ mutationFn: (workId: string) => jobCardsApi.cancelWork(job.id, workId), onSuccess: refresh, onError });

  return (
    <Card title={<span className="flex items-center gap-2"><Wrench className="h-4 w-4" /> Additional work</span>}
      actions={canEdit && !isCustomer && ["INSPECTION", "WORK_IN_PROGRESS", "WAITING_APPROVAL"].includes(job.status) &&
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> Request</Button>}>
      {job.additional_work?.length ? (
        <ul className="space-y-3">
          {job.additional_work.map((w) => (
            <li key={w.id} className={cn("rounded-xl p-3 ring-1", w.status === "PENDING" ? "bg-amber-50/60 ring-amber-200" : "bg-white ring-slate-200")}>
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-slate-800">{w.description}</p>
                <StatusBadge status={w.status} />
              </div>
              <p className="mt-1 text-sm font-semibold text-brand-700">{inr(w.estimated_cost)} <span className="text-xs font-normal text-slate-400">+ GST</span></p>
              {w.status === "PENDING" && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {(isCustomer || canEdit) && <>
                    <Button size="sm" variant="success" loading={respond.isPending} onClick={() => respond.mutate({ workId: w.id, approve: true })}><CheckCircle2 className="h-4 w-4" /> Approve</Button>
                    <Button size="sm" variant="danger" loading={respond.isPending} onClick={() => respond.mutate({ workId: w.id, approve: false })}><XCircle className="h-4 w-4" /> Decline</Button>
                  </>}
                  {!isCustomer && canEdit && <Button size="sm" variant="ghost" onClick={() => withdraw.mutate(w.id)}>Withdraw</Button>}
                </div>
              )}
              {!isCustomer && w.status === "PENDING" && <p className="mt-2 text-xs text-slate-500">Approve/decline here only to record the customer's answer given by phone.</p>}
            </li>
          ))}
        </ul>
      ) : <p className="text-sm text-slate-500">No additional work requested.</p>}
      <Modal open={open} onClose={() => setOpen(false)} title="Request additional work"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={request.isPending} disabled={!description || !cost} onClick={() => request.mutate()}>Send</Button></>}>
        <div className="space-y-4">
          <Textarea label="What's needed?" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Front-left tyre worn below limit — replace" />
          <Input label="Estimated cost (₹, before GST)" type="number" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} />
        </div>
      </Modal>
    </Card>
  );
}

export function JobCardDetailPage({ backTo }: { backTo: string }) {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const canUpdate = !isCustomer && Boolean(user?.permissions.includes("JOB_CARD_UPDATE"));
  const toast = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [details, setDetails] = useState<Partial<JobCard>>({});
  const [confirmComplete, setConfirmComplete] = useState(false);

  const job = useQuery({ queryKey: ["job-cards", id], queryFn: () => jobCardsApi.get(id) });
  const set = (j: JobCard) => { queryClient.setQueryData(["job-cards", id], j); queryClient.invalidateQueries({ queryKey: ["bookings"] }); };
  const onError = (err: unknown) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error");
  const start = useMutation({ mutationFn: () => jobCardsApi.startWork(id), onSuccess: (j) => { set(j); toast.show("Work started — customer notified.", "success"); }, onError });
  const complete = useMutation({
    mutationFn: () => jobCardsApi.complete(id),
    onSuccess: (j) => { set(j); setConfirmComplete(false); toast.show("Job completed. The invoice is being generated.", "success"); },
    onError: (err) => { setConfirmComplete(false); onError(err); },
  });
  const close = useMutation({ mutationFn: () => jobCardsApi.close(id), onSuccess: set, onError });
  const saveDetails = useMutation({
    mutationFn: () => jobCardsApi.update(id, details),
    onSuccess: (j) => { set(j); setDetails({}); toast.show("Saved.", "success"); },
    onError,
  });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("image", file);
      form.append("stage", job.data?.status === "COMPLETED" ? "AFTER" : "BEFORE");
      return jobCardsApi.uploadPhoto(id, form);
    },
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["job-cards", id] }); toast.show("Photo uploaded.", "success"); },
    onError: (err) => toast.show(err instanceof ApiError ? Object.values(err.fieldErrors())[0] ?? err.message : "Upload failed.", "error"),
  });

  if (job.isLoading) return <Skeleton rows={6} />;
  if (!job.data) return <Alert tone="danger">Job card not found.</Alert>;
  const j = job.data;
  const editable = canUpdate && EDITABLE.includes(j.status);
  const field = (k: keyof JobCard) => ({
    value: String(details[k] ?? j[k] ?? ""), disabled: !editable,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setDetails({ ...details, [k]: k === "odometer" ? Number(e.target.value) || null : e.target.value }),
  });

  return (
    <>
      <Link to={backTo} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="h-4 w-4" /> Job cards</Link>
      <PageHeader title={`${j.vehicle.brand} ${j.vehicle.model}`} description={`${j.job_card_number} · ${j.vehicle.registration_number} · ${j.booking.service}`}
        actions={<StatusBadge status={j.status} label={titleCase(j.status)} />} />

      {canUpdate && (
        <div className="stagger mb-6 flex flex-wrap gap-2">
          {["OPEN", "INSPECTION"].includes(j.status) && <Button loading={start.isPending} onClick={() => start.mutate()}><Play className="h-4 w-4" /> Start work</Button>}
          {j.status === "WORK_IN_PROGRESS" && <Button variant="success" onClick={() => setConfirmComplete(true)}><CheckCircle2 className="h-4 w-4" /> Complete job</Button>}
          {j.status === "COMPLETED" && <Button variant="secondary" loading={close.isPending} onClick={() => close.mutate()}>Close job card</Button>}
          {editable && (
            <>
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
              <Button variant="secondary" loading={upload.isPending} onClick={() => fileRef.current?.click()}><Camera className="h-4 w-4" /> Add photo</Button>
            </>
          )}
        </div>
      )}
      {j.status === "WAITING_APPROVAL" && <div className="mb-4"><Alert tone="warning">{isCustomer ? "Please review the additional work below." : "Waiting for the customer to approve additional work."}</Alert></div>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {!isCustomer && <InspectionPanel job={j} canEdit={editable} />}
          <AdditionalWorkPanel job={j} isCustomer={isCustomer} canEdit={editable} />
          <PartsPanel job={j} canEdit={editable} />
        </div>
        <div className="space-y-6">
          <Card title="Vehicle check-in" actions={Object.keys(details).length > 0 && <Button size="sm" loading={saveDetails.isPending} onClick={() => saveDetails.mutate()}>Save</Button>}>
            <div className="space-y-3">
              <Input label="Odometer (km)" type="number" inputMode="numeric" {...field("odometer")} />
              <Select label="Fuel level" {...field("fuel_level")}>
                <option value="">—</option>
                {["EMPTY", "QUARTER", "HALF", "THREE_QUARTER", "FULL"].map((f) => <option key={f} value={f}>{titleCase(f)}</option>)}
              </Select>
              <Textarea label="Existing damage" {...field("existing_damage")} />
              <Textarea label="Customer requests" {...field("customer_requests")} />
              {!isCustomer && <Textarea label="Technician notes" {...field("technician_notes")} />}
            </div>
          </Card>
          {Boolean(j.photos?.length) && (
            <Card title="Photos">
              <div className="grid grid-cols-3 gap-2">
                {j.photos!.map((p) => (
                  <a key={p.id} href={p.image} target="_blank" rel="noreferrer" className="group relative block aspect-square overflow-hidden rounded-xl bg-slate-100">
                    <img src={p.image} alt={p.caption || p.stage} loading="lazy" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
                    <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 text-[10px] text-white">{titleCase(p.stage)}</span>
                  </a>
                ))}
              </div>
            </Card>
          )}
          <Card title="Booking">
            <p className="text-sm text-slate-700">{j.customer.full_name} · {j.customer.phone}</p>
            <p className="mt-1 text-xs text-slate-500">Opened {formatDateTime(j.created_at)}</p>
            <Link to={`${backTo.replace("job-cards", "bookings")}/${j.booking.id}`} className="mt-3 inline-block text-sm font-medium text-brand-600 hover:underline">{j.booking.booking_number} →</Link>
          </Card>
        </div>
      </div>
      <ConfirmDialog open={confirmComplete} title="Complete this job?" tone="success" confirmLabel="Complete"
        message="The booking is marked completed, the invoice is generated and the customer is told their vehicle is ready."
        loading={complete.isPending} onCancel={() => setConfirmComplete(false)} onConfirm={() => complete.mutate()} />
    </>
  );
}
