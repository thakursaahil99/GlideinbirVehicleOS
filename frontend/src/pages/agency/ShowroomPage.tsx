import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, ShoppingCart } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { showroomApi, type VehicleModel, type VehicleSale } from "@/api/showroom";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader, StatsCard } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import { formatDate } from "@/utils/format";

type Form = Record<string, string>;
const TYPES = [["SCOOTER", "Scooter"], ["BIKE", "Bike"], ["EV", "Electric"], ["CAR", "Car"], ["OTHER", "Other"]];
const FUELS = [["PETROL", "Petrol"], ["ELECTRIC", "Electric"], ["CNG", "CNG"], ["DIESEL", "Diesel"], ["HYBRID", "Hybrid"]];
const rupees = (v: string | null) => (v == null || v === "" ? "—" : `₹${Number(v).toLocaleString("en-IN")}`);
const today = () => new Date().toISOString().slice(0, 10);

/** Generic form modal: prefilled values, field errors from the API, one save call. */
function FormModal({ open, title, initial, fields, save, success, submitLabel, onClose }: {
  open: boolean; title: string; initial: Form; submitLabel: string; success: string;
  fields: { k: string; label: string; type?: string; options?: string[][]; wide?: boolean }[];
  save: (form: Form) => Promise<unknown>; onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Reset only when the dialog opens — `initial` is rebuilt on every parent render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) { setForm(initial); setErrors({}); } }, [open]);
  const mutation = useMutation({
    mutationFn: () => save(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" && /year|cc|price/.test(k) ? null : v])) as Form),
    onSuccess: () => { toast.show(success, "success"); queryClient.invalidateQueries({ queryKey: ["showroom"] }); onClose(); },
    onError: (err) => { if (err instanceof ApiError) { setErrors(err.fieldErrors()); toast.show(err.message, "error"); } },
  });
  return (
    <Modal open={open} title={title} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={mutation.isPending} onClick={() => mutation.mutate()}>{submitLabel}</Button></>}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}>
        {fields.map((f) => {
          const common = { label: f.label, value: form[f.k] ?? "", error: errors[f.k], wrapperClassName: f.wide ? "sm:col-span-2" : undefined,
            onChange: (e: { target: { value: string } }) => setForm((s) => ({ ...s, [f.k]: e.target.value })) };
          return f.options
            ? <Select key={f.k} {...common}>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
            : <Input key={f.k} type={f.type ?? "text"} inputMode={f.type === "number" ? "decimal" : undefined} {...common} />;
        })}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

const MODEL_FIELDS = [
  { k: "vehicle_type", label: "Type", options: TYPES }, { k: "brand", label: "Brand" },
  { k: "name", label: "Model name" }, { k: "variant", label: "Variant (optional)" },
  { k: "launch_year", label: "Launch year", type: "number" }, { k: "fuel_type", label: "Fuel", options: FUELS },
  { k: "engine_cc", label: "Engine cc", type: "number" }, { k: "ex_showroom_price", label: "Ex-showroom price (₹)", type: "number" },
  { k: "stock_quantity", label: "Units in stock", type: "number" }, { k: "minimum_stock", label: "Alert when stock ≤", type: "number" },
  { k: "colours", label: "Colours (comma separated)", wide: true }, { k: "notes", label: "Notes", wide: true },
];

const SALE_FIELDS = [
  { k: "buyer_name", label: "Buyer name" }, { k: "buyer_phone", label: "Buyer phone", type: "tel" },
  { k: "buyer_email", label: "Buyer e-mail (optional)", type: "email" }, { k: "sold_on", label: "Sold on", type: "date" },
  { k: "buyer_address", label: "Buyer address", wide: true },
  { k: "sale_price", label: "Sale price (₹)", type: "number" }, { k: "payment_mode", label: "Payment", options: [["CASH", "Cash"], ["UPI", "UPI"], ["CARD", "Card"], ["FINANCE", "Finance / loan"], ["BANK", "Bank transfer"]] },
  { k: "colour", label: "Colour" }, { k: "invoice_number", label: "Invoice no." },
  { k: "chassis_number", label: "Chassis no." }, { k: "engine_number", label: "Engine no." },
  { k: "registration_number", label: "Registration no." }, { k: "notes", label: "Notes" },
];

const modelForm = (m: VehicleModel | null): Form => ({
  vehicle_type: m?.vehicle_type ?? "SCOOTER", brand: m?.brand ?? "", name: m?.name ?? "", variant: m?.variant ?? "",
  launch_year: m?.launch_year != null ? String(m.launch_year) : String(new Date().getFullYear()), fuel_type: m?.fuel_type ?? "PETROL",
  engine_cc: m?.engine_cc != null ? String(m.engine_cc) : "", ex_showroom_price: m?.ex_showroom_price ?? "",
  stock_quantity: String(m?.stock_quantity ?? 0), minimum_stock: String(m?.minimum_stock ?? 0), colours: m?.colours ?? "", notes: m?.notes ?? "",
});

const saleForm = (s: VehicleSale | null, m?: VehicleModel | null): Form => ({
  buyer_name: s?.buyer_name ?? "", buyer_phone: s?.buyer_phone ?? "", buyer_email: s?.buyer_email ?? "", sold_on: s?.sold_on ?? today(),
  buyer_address: s?.buyer_address ?? "", sale_price: s?.sale_price ?? m?.ex_showroom_price ?? "", payment_mode: s?.payment_mode || "CASH",
  colour: s?.colour ?? "", invoice_number: s?.invoice_number ?? "", chassis_number: s?.chassis_number ?? "",
  engine_number: s?.engine_number ?? "", registration_number: s?.registration_number ?? "", notes: s?.notes ?? "",
});

export function ShowroomPage() {
  const { user } = useAuth();
  const canManage = user?.role === "AGENCY_ADMIN" || user?.role === "AGENCY_MANAGER";
  const toast = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"models" | "sales">("models");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [editModel, setEditModel] = useState<VehicleModel | null | undefined>(undefined);
  const [selling, setSelling] = useState<VehicleModel | null>(null);
  const [stockFor, setStockFor] = useState<VehicleModel | null>(null);
  const [editSale, setEditSale] = useState<VehicleSale | null>(null);
  const [cancelling, setCancelling] = useState<VehicleSale | null>(null);

  const models = useQuery({ queryKey: ["showroom", "models", { search, type, page }], queryFn: () => showroomApi.models({ search, vehicle_type: type, page }),
    placeholderData: keepPreviousData, enabled: tab === "models" });
  const sales = useQuery({ queryKey: ["showroom", "sales", { search, page }], queryFn: () => showroomApi.sales({ search, page }),
    placeholderData: keepPreviousData });
  const lowStock = useQuery({ queryKey: ["showroom", "low"], queryFn: () => showroomApi.models({ low_stock: true, page_size: 1 }) });

  const cancel = useMutation({
    mutationFn: (s: VehicleSale) => showroomApi.cancelSale(s.id),
    onSuccess: () => { toast.show("Sale cancelled — unit returned to stock.", "success"); queryClient.invalidateQueries({ queryKey: ["showroom"] }); setCancelling(null); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not cancel.", "error"),
  });

  const switchTab = (t: "models" | "sales") => { setTab(t); setPage(1); setSearch(""); };

  return (
    <>
      <PageHeader title="Showroom" description="Every scooter and bike model you sell, units in stock, and who bought each one."
        actions={canManage && <Button onClick={() => setEditModel(null)}><Plus className="h-4 w-4" /> New model</Button>} />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatsCard label="Models" value={models.data?.pagination.count ?? "—"} />
        <StatsCard label="Low / out of stock" value={lowStock.data?.pagination.count ?? "—"} />
        <StatsCard label="Units sold" value={sales.data?.pagination.count ?? "—"} />
      </div>

      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="inline-flex rounded-xl bg-slate-100 p-1 text-sm">
            {(["models", "sales"] as const).map((t) => (
              <button key={t} type="button" onClick={() => switchTab(t)}
                className={`rounded-lg px-4 py-1.5 font-medium transition-all duration-200 ${tab === t ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                {t === "models" ? "Models & stock" : "Sales"}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder={tab === "models" ? "Search brand, model…" : "Search buyer, phone, chassis…"} />
            {tab === "models" && (
              <Select aria-label="Filter by type" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} wrapperClassName="sm:w-40">
                <option value="">All types</option>
                {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            )}
          </div>
        </div>

        {tab === "models" ? (
          <>
            <DataTable<VehicleModel>
              rows={models.data?.items} loading={models.isFetching} rowKey={(m) => m.id}
              emptyTitle="No vehicle models yet"
              columns={[
                { key: "model", header: "Model", render: (m) => (
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{m.brand} {m.name}{m.variant && <span className="text-slate-500"> · {m.variant}</span>}</p>
                    <p className="truncate text-xs text-slate-500">{m.vehicle_type_display}{m.launch_year ? ` · ${m.launch_year}` : ""}{m.engine_cc ? ` · ${m.engine_cc} cc` : ""}{m.colours ? ` · ${m.colours}` : ""}</p>
                  </div>
                ) },
                { key: "price", header: "Ex-showroom", render: (m) => rupees(m.ex_showroom_price), hideOnMobile: true },
                { key: "stock", header: "Stock", render: (m) => (
                  <div className="flex items-center gap-2">
                    <span className="font-semibold tabular-nums text-slate-900">{m.stock_quantity}</span>
                    {m.stock_quantity === 0 ? <StatusBadge status="OUT_OF_STOCK" /> : m.is_low_stock ? <StatusBadge status="LOW_STOCK" /> : null}
                  </div>
                ) },
                { key: "actions", header: "", className: "text-right", render: (m) => canManage && (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    <Button size="sm" variant="success" disabled={m.stock_quantity < 1} onClick={() => setSelling(m)}><ShoppingCart className="h-3.5 w-3.5" /> Sell</Button>
                    <Button size="sm" variant="secondary" onClick={() => setStockFor(m)}>Stock</Button>
                    <Button size="sm" variant="secondary" onClick={() => setEditModel(m)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                  </div>
                ) },
              ]}
            />
            <Pagination meta={models.data?.pagination} onPageChange={setPage} />
          </>
        ) : (
          <>
            <DataTable<VehicleSale>
              rows={sales.data?.items} loading={sales.isFetching} rowKey={(s) => s.id}
              emptyTitle="No sales recorded yet"
              columns={[
                { key: "buyer", header: "Sold to", render: (s) => (
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{s.buyer_name}</p>
                    <p className="truncate text-xs text-slate-500">{s.buyer_phone}{s.buyer_address ? ` · ${s.buyer_address}` : ""}</p>
                  </div>
                ) },
                { key: "vehicle", header: "Vehicle", render: (s) => (
                  <div className="min-w-0">
                    <p className="text-slate-800">{s.vehicle_model_name}{s.colour ? ` · ${s.colour}` : ""}</p>
                    <p className="truncate font-mono text-xs text-slate-500">{[s.registration_number, s.chassis_number].filter(Boolean).join(" · ") || "—"}</p>
                  </div>
                ) },
                { key: "price", header: "Price", render: (s) => rupees(s.sale_price), hideOnMobile: true },
                { key: "date", header: "Sold on", render: (s) => <span>{formatDate(s.sold_on)}{s.sold_by_name && <span className="block text-xs text-slate-500">by {s.sold_by_name}</span>}</span>, hideOnMobile: true },
                { key: "actions", header: "", className: "text-right", render: (s) => canManage && (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    <Button size="sm" variant="secondary" onClick={() => setEditSale(s)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => setCancelling(s)}>Cancel sale</Button>
                  </div>
                ) },
              ]}
            />
            <Pagination meta={sales.data?.pagination} onPageChange={setPage} />
          </>
        )}
      </Card>

      <FormModal open={editModel !== undefined} title={editModel ? `Edit ${editModel.brand} ${editModel.name}` : "New vehicle model"}
        initial={modelForm(editModel ?? null)} fields={MODEL_FIELDS} submitLabel={editModel ? "Save changes" : "Add model"}
        success={editModel ? "Model updated." : "Model added."}
        save={(f) => (editModel ? showroomApi.updateModel(editModel.id, f) : showroomApi.createModel(f))}
        onClose={() => setEditModel(undefined)} />

      <FormModal open={Boolean(selling)} title={selling ? `Sell ${selling.brand} ${selling.name}` : ""} initial={saleForm(null, selling)}
        fields={SALE_FIELDS} submitLabel="Record sale" success="Sale recorded — stock updated."
        save={(f) => showroomApi.createSale({ ...f, vehicle_model: selling!.id })} onClose={() => setSelling(null)} />

      <FormModal open={Boolean(editSale)} title="Edit sale" initial={saleForm(editSale)} fields={SALE_FIELDS}
        submitLabel="Save changes" success="Sale updated." save={(f) => showroomApi.updateSale(editSale!.id, f)} onClose={() => setEditSale(null)} />

      <FormModal open={Boolean(stockFor)} title={stockFor ? `Stock · ${stockFor.brand} ${stockFor.name} (now ${stockFor.stock_quantity})` : ""}
        initial={{ quantity: "", note: "" }} submitLabel="Update stock" success="Stock updated."
        fields={[{ k: "quantity", label: "Units (+ received, − removed)", type: "number" }, { k: "note", label: "Note (e.g. dealer invoice)" }]}
        save={(f) => showroomApi.adjustStock(stockFor!.id, Number(f.quantity), f.note)} onClose={() => setStockFor(null)} />

      <ConfirmDialog open={Boolean(cancelling)} title="Cancel this sale?" tone="danger" confirmLabel="Cancel sale" loading={cancel.isPending}
        message={cancelling ? `${cancelling.vehicle_model_name} sold to ${cancelling.buyer_name} will be removed and the unit returned to stock.` : ""}
        onCancel={() => setCancelling(null)} onConfirm={() => cancelling && cancel.mutate(cancelling)} />
    </>
  );
}
