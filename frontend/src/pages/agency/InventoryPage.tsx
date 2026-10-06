import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownUp, History, IndianRupee, MapPin, PackageX, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { inventoryApi } from "@/api/operations";
import { organizationsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, PageHeader, Skeleton, StatsCard } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select, Textarea } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Checkbox, Tabs } from "@/components/ui/Tabs";
import { ImportButton } from "@/components/ui/ImportButton";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { Part, PartCategory, PartFitment, Supplier } from "@/types/operations";
import { formatDate, formatDateTime, inr, titleCase } from "@/utils/format";

const UNITS = ["PCS", "LITRE", "KG", "SET", "METRE"];
const VEHICLE_TYPES = [
  { value: "BIKE", label: "Bike" },
  { value: "SCOOTER", label: "Scooter / Scooty" },
  { value: "CAR", label: "Car" },
  { value: "EV", label: "Electric vehicle" },
  { value: "OTHER", label: "Other" },
];
const STOCK_LABEL = { IN_STOCK: "In stock", LOW_STOCK: "Low stock", OUT_OF_STOCK: "Out of stock" } as const;

function useCatalog(organization = "") {
  const categories = useQuery({ queryKey: ["inventory", "categories", organization], queryFn: () => inventoryApi.categories(organization) });
  const suppliers = useQuery({ queryKey: ["inventory", "suppliers", organization], queryFn: () => inventoryApi.suppliers({ organization }) });
  return { categories: categories.data ?? [], suppliers: suppliers.data?.items ?? [] };
}

function fitmentLabel(f: PartFitment) {
  const years = f.year_from || f.year_to ? ` ${f.year_from ?? "…"}–${f.year_to ?? "…"}` : "";
  return `${f.brand} ${f.model || "(all models)"}${years}`;
}

function StockBadge({ part }: { part: Part }) {
  return <StatusBadge status={part.stock_status} label={STOCK_LABEL[part.stock_status]} />;
}

const EMPTY_FORM = {
  name: "", sku: "", brand: "", purchase_price: "", selling_price: "", minimum_stock: "0", unit: "PCS",
  category: "", preferred_supplier: "", hsn_code: "", rack_location: "", description: "", universal: false,
};

function PartModal({ open, part, onClose }: { open: boolean; part?: Part | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const [agency, setAgency] = useState("");
  const org = part?.organization ?? agency;
  const agencies = useQuery({ queryKey: ["orgs", "picker"], queryFn: () => organizationsApi.list({ page_size: 100, status: "ACTIVE" }), enabled: isSuperAdmin && open && !part });
  const { categories, suppliers } = useCatalog(isSuperAdmin ? org : "");
  const [form, setForm] = useState(EMPTY_FORM);
  const [fitments, setFitments] = useState<PartFitment[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(part
      ? {
          name: part.name, sku: part.sku ?? "", brand: part.brand ?? "", purchase_price: String(part.purchase_price ?? ""),
          selling_price: String(part.selling_price ?? ""), minimum_stock: String(part.minimum_stock ?? "0"), unit: part.unit ?? "PCS",
          category: part.category ?? "", preferred_supplier: part.preferred_supplier ?? "", hsn_code: part.hsn_code ?? "",
          rack_location: part.rack_location ?? "", description: part.description ?? "", universal: part.universal ?? false,
        }
      : EMPTY_FORM);
    setFitments(part?.fitments?.map((f) => ({ ...f })) ?? []);
  }, [open, part]);
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        category: form.category || null,
        preferred_supplier: form.preferred_supplier || null,
        fitments: form.universal ? [] : fitments.filter((f) => f.brand.trim()),
        ...(isSuperAdmin && !part ? { organization: agency } : {}),
      };
      return part ? inventoryApi.update(part.id, payload as Partial<Part>) : inventoryApi.create(payload as Partial<Part>);
    },
    onSuccess: () => {
      toast.show(part ? "Part updated." : "Part added. Record a purchase to add stock.", "success");
      queryClient.invalidateQueries({ queryKey: ["parts"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      onClose();
    },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  const bind = (k: Exclude<keyof typeof form, "universal">) => ({
    value: form[k], error: errors[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value }),
  });
  const setFit = (i: number, patch: Partial<PartFitment>) => setFitments(fitments.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const year = (v: string) => (v ? Number(v) : null);

  return (
    <Modal open={open} onClose={onClose} title={part ? `Edit ${part.name}` : "New part"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>{part ? "Save changes" : "Add part"}</Button></>}>
      <div className="space-y-5">
        {isSuperAdmin && !part && (
          <Select label="Agency" value={agency} error={errors.organization} onChange={(e) => { setAgency(e.target.value); setForm({ ...form, category: "", preferred_supplier: "" }); }}>
            <option value="">Choose the agency this part belongs to…</option>
            {agencies.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="Name" {...bind("name")} wrapperClassName="sm:col-span-2" />
          <Input label="SKU" {...bind("sku")} />
          <Input label="Brand" {...bind("brand")} />
          <Select label="Category" {...bind("category")}>
            <option value="">Uncategorised</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select label="Supplier / dealer" {...bind("preferred_supplier")}>
            <option value="">None</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Input label="Purchase price (₹)" type="number" inputMode="decimal" {...bind("purchase_price")} />
          <Input label="Selling price (₹)" type="number" inputMode="decimal" {...bind("selling_price")} />
          <Input label="Re-order level" type="number" inputMode="decimal" {...bind("minimum_stock")} />
          <Select label="Unit" {...bind("unit")}>{UNITS.map((u) => <option key={u} value={u}>{titleCase(u)}</option>)}</Select>
          <Input label="HSN code" inputMode="numeric" placeholder="e.g. 8708" {...bind("hsn_code")} />
          <Input label="Rack / shelf" placeholder="e.g. Rack B · Shelf 3" {...bind("rack_location")} />
          <Textarea label="Notes" {...bind("description")} wrapperClassName="sm:col-span-2" rows={2} />
        </div>

        <fieldset className="rounded-2xl bg-slate-50 p-4 ring-1 ring-slate-200/70">
          <legend className="px-1 text-sm font-semibold text-slate-800">Fits which vehicles?</legend>
          <Checkbox checked={form.universal} onChange={(v) => setForm({ ...form, universal: v })} label="Universal: fits every vehicle" />
          {!form.universal && (
            <div className="mt-3 space-y-3">
              {fitments.length === 0 && <p className="text-xs text-slate-500">Add the bike / scooty / car models this part fits. Leave model blank for every model of a brand.</p>}
              {fitments.map((f, i) => (
                <div key={i} className="grid animate-fade-up grid-cols-2 gap-2 rounded-xl bg-white p-3 ring-1 ring-slate-200 sm:grid-cols-6">
                  <Select aria-label="Vehicle type" value={f.vehicle_type} onChange={(e) => setFit(i, { vehicle_type: e.target.value })} wrapperClassName="col-span-2 sm:col-span-2">
                    <option value="">Any type</option>
                    {VEHICLE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label.split(" /")[0]}</option>)}
                  </Select>
                  <Input aria-label="Vehicle brand" placeholder="Brand (Honda)" value={f.brand} onChange={(e) => setFit(i, { brand: e.target.value })} wrapperClassName="sm:col-span-2" />
                  <Input aria-label="Vehicle model" placeholder="Model (Activa 6G)" value={f.model} onChange={(e) => setFit(i, { model: e.target.value })} wrapperClassName="sm:col-span-2" />
                  <Input aria-label="From year" placeholder="From year" type="number" inputMode="numeric" value={f.year_from ?? ""} onChange={(e) => setFit(i, { year_from: year(e.target.value) })} wrapperClassName="sm:col-span-2" />
                  <Input aria-label="To year" placeholder="To year" type="number" inputMode="numeric" value={f.year_to ?? ""} onChange={(e) => setFit(i, { year_to: year(e.target.value) })} wrapperClassName="sm:col-span-2" />
                  <div className="col-span-2 flex justify-end sm:col-span-2">
                    <Button size="sm" variant="ghost" onClick={() => setFitments(fitments.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /> Remove</Button>
                  </div>
                </div>
              ))}
              <Button size="sm" variant="secondary" onClick={() => setFitments([...fitments, { vehicle_type: "", brand: "", model: "", year_from: null, year_to: null }])}>
                <Plus className="h-4 w-4" /> Add vehicle
              </Button>
              {errors.fitments && <p className="text-xs text-rose-600">{errors.fitments}</p>}
            </div>
          )}
        </fieldset>
      </div>
    </Modal>
  );
}

function MoveModal({ part, onClose }: { part: Part | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { suppliers } = useCatalog(user?.role === "SUPER_ADMIN" ? part?.organization ?? "" : "");
  const [type, setType] = useState("PURCHASE");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [supplier, setSupplier] = useState("");
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  useEffect(() => { if (part) setSupplier(part.preferred_supplier ?? ""); }, [part]);
  const move = useMutation({
    mutationFn: () => inventoryApi.move(part!.id, {
      transaction_type: type, quantity: qty, note, reference,
      ...(price ? { unit_price: price } : {}),
      ...(type === "PURCHASE" && supplier ? { supplier } : {}),
    }),
    onSuccess: (tx) => {
      toast.show(`Stock is now ${Number(tx.balance_after)}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["parts"] });
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
      setQty(""); setNote(""); setReference(""); setPrice("");
      onClose();
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not update stock.", "error"),
  });
  return (
    <Modal open={Boolean(part)} onClose={onClose} title={part ? `Stock · ${part.name}` : ""}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={move.isPending} disabled={!qty} onClick={() => move.mutate()}>Save</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-slate-600">Current stock: <b>{part && Number(part.stock_quantity)} {part && titleCase(part.unit)}</b></p>
        <Select label="Movement" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="PURCHASE">Purchase (stock in)</option>
          <option value="RETURN">Return (stock in)</option>
          <option value="SALE">Counter sale (stock out)</option>
          <option value="ADJUSTMENT">Adjustment (+/−, needs note)</option>
        </Select>
        {type === "PURCHASE" && (
          <Select label="Bought from" value={supplier} onChange={(e) => setSupplier(e.target.value)}>
            <option value="">Not recorded</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label={type === "ADJUSTMENT" ? "Quantity (use − to reduce)" : "Quantity"} type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
          <Input label="Rate per unit (₹)" type="number" inputMode="decimal" placeholder={part ? String(Number(type === "PURCHASE" ? part.purchase_price : part.selling_price)) : ""} value={price} onChange={(e) => setPrice(e.target.value)} />
        </div>
        <Input label="Reference (bill / invoice no.)" value={reference} onChange={(e) => setReference(e.target.value)} />
        <Input label={type === "ADJUSTMENT" ? "Reason (required)" : "Note"} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
    </Modal>
  );
}

function LedgerModal({ part, onClose }: { part: Part | null; onClose: () => void }) {
  const ledger = useQuery({ queryKey: ["parts", part?.id, "ledger"], queryFn: () => inventoryApi.transactions(part!.id), enabled: Boolean(part) });
  return (
    <Modal open={Boolean(part)} onClose={onClose} title={part ? `Ledger · ${part.name}` : ""}>
      {ledger.isLoading ? <Skeleton rows={4} /> : (
        <ul className="divide-y divide-slate-100 text-sm">
          {ledger.data?.items.map((t) => (
            <li key={t.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-800">{titleCase(t.transaction_type)}{t.job_card_number && ` · ${t.job_card_number}`}{t.supplier_name && ` · ${t.supplier_name}`}</p>
                <p className="truncate text-xs text-slate-500">{formatDateTime(t.created_at)}{t.created_by_name && ` · ${t.created_by_name}`}{t.reference && ` · ${t.reference}`}{t.note && ` · ${t.note}`}</p>
              </div>
              <span className={Number(t.quantity) < 0 ? "font-semibold text-rose-600" : "font-semibold text-emerald-600"}>{Number(t.quantity) > 0 ? "+" : ""}{Number(t.quantity)}</span>
              <span className="w-12 text-right text-slate-500">{Number(t.balance_after)}</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function PartCell({ p }: { p: Part }) {
  const { user } = useAuth();
  const showAgency = user?.role === "SUPER_ADMIN";
  return (
    <div className="min-w-0">
      <p className="font-medium text-slate-900">{p.name}</p>
      <p className="text-xs text-slate-500">{p.sku}{p.brand && ` · ${p.brand}`}{p.category_name && ` · ${p.category_name}`}</p>
      {showAgency && <p className="text-xs font-medium text-brand-700">{p.organization_name}</p>}
      {(p.rack_location || p.universal || p.fitments?.length > 0) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {p.rack_location && <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600"><MapPin className="h-3 w-3" />{p.rack_location}</span>}
          {p.universal && <span className="rounded-md bg-accent-400/15 px-1.5 py-0.5 text-[11px] font-medium text-accent-500">Universal</span>}
          {p.fitments?.slice(0, 3).map((f) => <span key={f.id ?? fitmentLabel(f)} className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[11px] text-brand-700">{fitmentLabel(f)}</span>)}
          {p.fitments?.length > 3 && <span className="text-[11px] text-slate-500">+{p.fitments.length - 3} more</span>}
        </div>
      )}
    </div>
  );
}

/** "Which parts do we have for this bike / scooty?": type → brand → model picker. */
function VehicleFinder({ partColumns }: { partColumns: (p: Part) => React.ReactNode }) {
  const [type, setType] = useState("");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [status, setStatus] = useState("");
  const options = useQuery({ queryKey: ["inventory", "fitment-options"], queryFn: inventoryApi.fitmentOptions });
  const brands = useMemo(() => [...new Set((options.data ?? []).filter((o) => !type || !o.vehicle_type || o.vehicle_type === type).map((o) => o.brand))].sort(), [options.data, type]);
  const models = useMemo(() => [...new Set((options.data ?? []).filter((o) => o.brand.toLowerCase() === brand.toLowerCase() && o.model && (!type || !o.vehicle_type || o.vehicle_type === type)).map((o) => o.model))].sort(), [options.data, brand, type]);
  const ready = brand.trim().length > 0;
  const results = useQuery({
    queryKey: ["parts", "compatible", { type, brand, model, year, status }],
    queryFn: () => inventoryApi.compatible({ vehicle_type: type, brand, model, year, stock_status: status, page_size: 100 }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });
  const rows = results.data?.items ?? [];
  const counts = { all: rows.length, in: rows.filter((p) => p.stock_status !== "OUT_OF_STOCK").length, out: rows.filter((p) => p.stock_status === "OUT_OF_STOCK").length };

  return (
    <Card>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Select label="Vehicle type" value={type} onChange={(e) => { setType(e.target.value); setBrand(""); setModel(""); }}>
          <option value="">Any type</option>
          {VEHICLE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
        <Input label="Brand" list="fit-brands" placeholder="Honda, Hero, TVS…" value={brand} onChange={(e) => { setBrand(e.target.value); setModel(""); }} />
        <Input label="Model" list="fit-models" placeholder={brand ? "All models" : "Pick a brand first"} disabled={!brand} value={model} onChange={(e) => setModel(e.target.value)} />
        <Input label="Year (optional)" type="number" inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />
        <datalist id="fit-brands">{brands.map((b) => <option key={b} value={b} />)}</datalist>
        <datalist id="fit-models">{models.map((m) => <option key={m} value={m} />)}</datalist>
      </div>

      {!ready ? (
        <EmptyState title="Pick a vehicle" description="Choose the type and brand (and model) to see every part that fits, and whether it's in stock." />
      ) : (
        <div className="mt-5">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {[{ v: "", label: `All (${counts.all})` }, { v: "IN_STOCK", label: "In stock" }, { v: "LOW_STOCK", label: "Low" }, { v: "OUT_OF_STOCK", label: "Out of stock" }].map((s) => (
              <button key={s.v} type="button" onClick={() => setStatus(s.v)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition ${status === s.v ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"}`}>
                {s.label}
              </button>
            ))}
            {!status && rows.length > 0 && (
              <span className="ml-auto text-xs text-slate-500">
                <b className="text-emerald-600">{counts.in}</b> available · <b className="text-rose-600">{counts.out}</b> out of stock
              </span>
            )}
          </div>
          <DataTable<Part>
            rows={rows}
            loading={results.isFetching}
            rowKey={(p) => p.id}
            emptyTitle="No parts tagged for this vehicle"
            emptyDescription="Edit a part and add this model under “Fits which vehicles?”."
            columns={[
              { key: "name", header: "Part", render: (p) => <PartCell p={p} /> },
              { key: "status", header: "Availability", render: (p) => <StockBadge part={p} /> },
              { key: "stock", header: "Stock", render: (p) => <span className="whitespace-nowrap">{Number(p.stock_quantity)} {titleCase(p.unit)}</span> },
              { key: "sell", header: "Price", render: (p) => inr(p.selling_price) },
              { key: "actions", header: "", className: "text-right", render: partColumns },
            ]}
          />
        </div>
      )}
    </Card>
  );
}

function SupplierModal({ open, supplier, onClose }: { open: boolean; supplier?: Supplier | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const empty = { name: "", contact_person: "", phone: "", email: "", gst_number: "", address: "", notes: "" };
  const [form, setForm] = useState(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(supplier ? { name: supplier.name, contact_person: supplier.contact_person, phone: supplier.phone, email: supplier.email, gst_number: supplier.gst_number, address: supplier.address, notes: supplier.notes } : empty);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, supplier]);
  const save = useMutation({
    mutationFn: () => (supplier ? inventoryApi.updateSupplier(supplier.id, form) : inventoryApi.createSupplier(form)),
    onSuccess: () => { toast.show(supplier ? "Supplier updated." : "Supplier added.", "success"); queryClient.invalidateQueries({ queryKey: ["inventory"] }); onClose(); },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  const bind = (k: keyof typeof form) => ({ value: form[k], error: errors[k], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value }) });
  return (
    <Modal open={open} onClose={onClose} title={supplier ? `Edit ${supplier.name}` : "New supplier"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>{supplier ? "Save changes" : "Add supplier"}</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Name" {...bind("name")} wrapperClassName="sm:col-span-2" />
        <Input label="Contact person" {...bind("contact_person")} />
        <Input label="Phone" type="tel" inputMode="tel" {...bind("phone")} />
        <Input label="E-mail" type="email" {...bind("email")} />
        <Input label="GSTIN" {...bind("gst_number")} />
        <Textarea label="Address" {...bind("address")} wrapperClassName="sm:col-span-2" rows={2} />
        <Textarea label="Notes" {...bind("notes")} wrapperClassName="sm:col-span-2" rows={2} />
      </div>
    </Modal>
  );
}

function SuppliersTab({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Supplier | null>(null);
  const list = useQuery({ queryKey: ["inventory", "suppliers", search], queryFn: () => inventoryApi.suppliers({ search }), placeholderData: keepPreviousData });
  const remove = useMutation({
    mutationFn: (s: Supplier) => inventoryApi.deleteSupplier(s.id),
    onSuccess: () => { toast.show("Supplier removed.", "success"); queryClient.invalidateQueries({ queryKey: ["inventory"] }); setRemoving(null); },
    onError: (err) => { toast.show(err instanceof ApiError ? err.message : "Could not remove supplier.", "error"); setRemoving(null); },
  });
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SearchBar value={search} onChange={setSearch} placeholder="Name, phone, GSTIN…" />
        {canManage && <div className="flex flex-wrap gap-2"><ImportButton resource="suppliers" invalidate={[["inventory"]]} /><Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> New supplier</Button></div>}
      </div>
      <DataTable<Supplier>
        rows={list.data?.items}
        loading={list.isFetching}
        rowKey={(s) => s.id}
        emptyTitle="No suppliers yet"
        emptyDescription="Add the dealers you buy parts from, then pick them when recording a purchase."
        columns={[
          { key: "name", header: "Supplier", render: (s) => <div className="min-w-0"><p className="font-medium text-slate-900">{s.name}</p><p className="text-xs text-slate-500">{[s.contact_person, s.phone].filter(Boolean).join(" · ") || "—"}</p></div> },
          { key: "gst", header: "GSTIN", render: (s) => s.gst_number || "—", hideOnMobile: true },
          { key: "parts", header: "Parts", render: (s) => s.parts_count },
          { key: "total", header: "Purchased", render: (s) => <span className="whitespace-nowrap">{inr(s.purchase_total)} <span className="text-xs text-slate-400">({s.purchase_count})</span></span> },
          { key: "last", header: "Last purchase", render: (s) => (s.last_purchase_at ? formatDate(s.last_purchase_at) : "—"), hideOnMobile: true },
          {
            key: "actions", header: "", className: "text-right",
            render: (s) => canManage && (
              <div className="flex justify-end gap-1.5">
                <Button size="sm" variant="secondary" onClick={() => setEditing(s)}>Edit</Button>
                <Button size="sm" variant="ghost" aria-label={`Remove ${s.name}`} onClick={() => setRemoving(s)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ),
          },
        ]}
      />
      <SupplierModal open={adding} onClose={() => setAdding(false)} />
      <SupplierModal open={Boolean(editing)} supplier={editing} onClose={() => setEditing(null)} />
      <ConfirmDialog open={Boolean(removing)} title="Remove supplier?" tone="danger" confirmLabel="Remove" loading={remove.isPending}
        message={`${removing?.name ?? ""} will be removed. Suppliers with purchase history can't be removed.`}
        onConfirm={() => removing && remove.mutate(removing)} onCancel={() => setRemoving(null)} />
    </Card>
  );
}

function CategoriesTab({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { categories } = useCatalog();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<PartCategory | null>(null);
  const [editName, setEditName] = useState("");
  const done = (msg: string) => { toast.show(msg, "success"); queryClient.invalidateQueries({ queryKey: ["inventory"] }); queryClient.invalidateQueries({ queryKey: ["parts"] }); };
  const fail = (err: unknown) => toast.show(err instanceof ApiError ? err.message : "Something went wrong.", "error");
  const create = useMutation({ mutationFn: () => inventoryApi.createCategory({ name }), onSuccess: () => { setName(""); done("Category added."); }, onError: fail });
  const rename = useMutation({ mutationFn: () => inventoryApi.updateCategory(editing!.id, { name: editName }), onSuccess: () => { setEditing(null); done("Category renamed."); }, onError: fail });
  const remove = useMutation({ mutationFn: (c: PartCategory) => inventoryApi.deleteCategory(c.id), onSuccess: () => done("Category removed. Its parts are now uncategorised."), onError: fail });
  return (
    <Card>
      {canManage && (
        <form className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
          <Input label="New category" placeholder="Engine, Brakes, Electrical, Oils…" value={name} onChange={(e) => setName(e.target.value)} wrapperClassName="flex-1" />
          <Button type="submit" loading={create.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" /> Add</Button>
        </form>
      )}
      {categories.length === 0 ? <EmptyState title="No categories yet" description="Group parts so they're quicker to find." /> : (
        <ul className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((c) => (
            <li key={c.id} className="flex items-center gap-3 rounded-2xl bg-white p-4 ring-1 ring-slate-200/70 transition hover:shadow-[var(--shadow-soft)]">
              {editing?.id === c.id ? (
                <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); rename.mutate(); }}>
                  <Input aria-label="Category name" value={editName} onChange={(e) => setEditName(e.target.value)} wrapperClassName="flex-1" autoFocus />
                  <Button size="sm" type="submit" loading={rename.isPending}>Save</Button>
                </form>
              ) : (
                <>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-slate-900">{c.name}</p>
                    <p className="text-xs text-slate-500">{c.parts_count} part{c.parts_count === 1 ? "" : "s"}</p>
                  </div>
                  {canManage && <Button size="sm" variant="ghost" onClick={() => { setEditing(c); setEditName(c.name); }}>Rename</Button>}
                  {canManage && <Button size="sm" variant="ghost" aria-label={`Remove ${c.name}`} onClick={() => remove.mutate(c)}><Trash2 className="h-4 w-4" /></Button>}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StockValueTab() {
  const summary = useQuery({ queryKey: ["inventory", "summary"], queryFn: inventoryApi.summary });
  if (summary.isLoading || !summary.data) return <Card><Skeleton rows={5} /></Card>;
  const s = summary.data;
  const max = Math.max(1, ...s.by_category.map((c) => Number(c.value)));
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Stock value by category">
        {s.by_category.length === 0 ? <EmptyState title="No stock yet" /> : (
          <ul className="space-y-3">
            {s.by_category.map((c) => (
              <li key={c.category}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-medium text-slate-800">{c.category} <span className="text-xs font-normal text-slate-400">· {c.parts} parts</span></span>
                  <span className="tabular-nums text-slate-700">{inr(c.value)}</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full origin-left animate-[grow_0.8s_var(--ease-out-expo)_both] rounded-full bg-gradient-to-r from-brand-500 to-accent-400" style={{ width: `${(Number(c.value) / max) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">At selling price this stock is worth <b className="text-slate-700">{inr(s.stock_value_retail)}</b>.</p>
      </Card>
      <Card title={`Not moving (no sale or job use in ${s.dead_stock_days} days)`}>
        {s.dead_stock.length === 0 ? <EmptyState title="Everything is moving" description="No idle stock right now." /> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {s.dead_stock.map((d) => (
              <li key={d.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-800">{d.name}</p>
                  <p className="text-xs text-slate-500">{d.sku} · {Number(d.stock_quantity)} {titleCase(d.unit)} · {d.last_out_at ? `last used ${formatDate(d.last_out_at)}` : "never used"}</p>
                </div>
                <span className="tabular-nums font-medium text-slate-700">{inr(d.value)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

type TabKey = "all" | "low" | "vehicle" | "suppliers" | "categories" | "value";

export function InventoryPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const canManage = user?.role === "AGENCY_ADMIN" || user?.role === "AGENCY_MANAGER" || isSuperAdmin;
  const [tab, setTab] = useState<TabKey>("all");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [moving, setMoving] = useState<Part | null>(null);
  const [editingPart, setEditingPart] = useState<Part | null>(null);
  const [ledger, setLedger] = useState<Part | null>(null);
  const { categories } = useCatalog();
  const isPartList = tab === "all" || tab === "low";

  const query = useQuery({
    queryKey: ["parts", { tab, search, page, category }],
    queryFn: () => inventoryApi.list({ low_stock: tab === "low" ? true : undefined, search, page, category }),
    placeholderData: keepPreviousData,
    enabled: isPartList,
  });
  const summary = useQuery({ queryKey: ["inventory", "summary"], queryFn: inventoryApi.summary });

  const partActions = (p: Part) => (
    <div className="flex justify-end gap-1.5">
      {canManage && <Button size="sm" variant="secondary" onClick={() => setEditingPart(p)}>Edit</Button>}
      {canManage && <Button size="sm" variant="secondary" onClick={() => setMoving(p)}>Stock</Button>}
      <Button size="sm" variant="ghost" aria-label="Ledger" onClick={() => setLedger(p)}><History className="h-4 w-4" /></Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Spare parts" description={user?.role === "SUPER_ADMIN" ? "Spare parts across every agency: stock, the vehicles they fit and suppliers (read-only)." : "Your spare parts, which vehicles they fit, stock levels, suppliers and every stock movement."}
        actions={canManage && (
          <div className="flex flex-wrap gap-2">
            <ImportButton resource="parts" invalidate={[["parts"], ["inventory"]]} />
            <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> New part</Button>
          </div>
        )} />
      <div className="stagger mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatsCard label="Parts tracked" value={summary.data?.parts ?? 0} icon={<ArrowDownUp className="h-5 w-5" />} />
        <StatsCard label="Stock value (cost)" value={summary.data ? inr(summary.data.stock_value_cost) : "—"} icon={<IndianRupee className="h-5 w-5" />} hint={summary.data ? `${inr(summary.data.stock_value_retail)} at selling price` : undefined} />
        <StatsCard label="Below re-order level" value={summary.data?.low_stock ?? 0} icon={<AlertTriangle className="h-5 w-5" />} />
        <StatsCard label="Out of stock" value={summary.data?.out_of_stock ?? 0} icon={<PackageX className="h-5 w-5" />} />
      </div>
      <Tabs<TabKey>
        items={[
          { key: "all", label: "All parts" }, { key: "low", label: "Re-order list" }, { key: "vehicle", label: "Find by vehicle" },
          { key: "suppliers", label: "Suppliers" }, { key: "categories", label: "Categories" }, { key: "value", label: "Stock value" },
        ]}
        active={tab}
        onChange={(k) => { setTab(k); setPage(1); }}
      />

      {isPartList && (
        <Card>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name, SKU, brand, HSN, rack…" />
            <Select aria-label="Category" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} wrapperClassName="sm:w-56">
              <option value="">All categories</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </div>
          <DataTable<Part>
            rows={query.data?.items}
            loading={query.isFetching}
            rowKey={(p) => p.id}
            emptyTitle={tab === "low" ? "Nothing to re-order" : "No parts yet"}
            columns={[
              { key: "name", header: "Part", render: (p) => <PartCell p={p} /> },
              {
                key: "stock", header: "Stock",
                render: (p) => <span className="flex flex-wrap items-center gap-1.5 whitespace-nowrap">{Number(p.stock_quantity)} {titleCase(p.unit)} {p.stock_status !== "IN_STOCK" && <StockBadge part={p} />}</span>,
              },
              { key: "sell", header: "Price", render: (p) => inr(p.selling_price), hideOnMobile: true },
              { key: "buy", header: "Cost", render: (p) => inr(p.purchase_price), hideOnMobile: true },
              { key: "supplier", header: "Supplier", render: (p) => p.preferred_supplier_name ?? "—", hideOnMobile: true },
              { key: "actions", header: "", className: "text-right", render: partActions },
            ]}
          />
          <Pagination meta={query.data?.pagination} onPageChange={setPage} />
        </Card>
      )}
      {tab === "vehicle" && <VehicleFinder partColumns={partActions} />}
      {tab === "suppliers" && <SuppliersTab canManage={canManage && !isSuperAdmin} />}
      {tab === "categories" && <CategoriesTab canManage={canManage && !isSuperAdmin} />}
      {tab === "value" && <StockValueTab />}

      <PartModal open={adding} onClose={() => setAdding(false)} />
      <PartModal open={Boolean(editingPart)} part={editingPart} onClose={() => setEditingPart(null)} />
      <MoveModal part={moving} onClose={() => setMoving(null)} />
      <LedgerModal part={ledger} onClose={() => setLedger(null)} />
    </>
  );
}
