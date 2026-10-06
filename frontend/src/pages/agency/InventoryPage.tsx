import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownUp, History, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { inventoryApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader, Skeleton, StatsCard } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { Part } from "@/types/operations";
import { formatDateTime, inr, titleCase } from "@/utils/format";

const UNITS = ["PCS", "LITRE", "KG", "SET", "METRE"];

function PartModal({ open, part, onClose }: { open: boolean; part?: Part | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", sku: "", brand: "", purchase_price: "", selling_price: "", minimum_stock: "0", unit: "PCS" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(part
      ? { name: part.name, sku: part.sku ?? "", brand: part.brand ?? "", purchase_price: String(part.purchase_price ?? ""), selling_price: String(part.selling_price ?? ""), minimum_stock: String(part.minimum_stock ?? "0"), unit: part.unit ?? "PCS" }
      : { name: "", sku: "", brand: "", purchase_price: "", selling_price: "", minimum_stock: "0", unit: "PCS" });
  }, [open, part]);
  const save = useMutation({
    mutationFn: () => (part ? inventoryApi.update(part.id, form) : inventoryApi.create(form)),
    onSuccess: () => { toast.show(part ? "Part updated." : "Part added. Record a purchase to add stock.", "success"); queryClient.invalidateQueries({ queryKey: ["parts"] }); onClose(); },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  const bind = (k: keyof typeof form) => ({ value: form[k], error: errors[k], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value }) });
  return (
    <Modal open={open} onClose={onClose} title={part ? `Edit ${part.name}` : "New part"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>{part ? "Save changes" : "Add part"}</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Name" {...bind("name")} wrapperClassName="sm:col-span-2" />
        <Input label="SKU" {...bind("sku")} />
        <Input label="Brand" {...bind("brand")} />
        <Input label="Purchase price (₹)" type="number" inputMode="decimal" {...bind("purchase_price")} />
        <Input label="Selling price (₹)" type="number" inputMode="decimal" {...bind("selling_price")} />
        <Input label="Re-order level" type="number" inputMode="decimal" {...bind("minimum_stock")} />
        <Select label="Unit" {...bind("unit")}>{UNITS.map((u) => <option key={u} value={u}>{titleCase(u)}</option>)}</Select>
      </div>
    </Modal>
  );
}

function MoveModal({ part, onClose }: { part: Part | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [type, setType] = useState("PURCHASE");
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const move = useMutation({
    mutationFn: () => inventoryApi.move(part!.id, { transaction_type: type, quantity: qty, note, reference }),
    onSuccess: (tx) => {
      toast.show(`Stock is now ${Number(tx.balance_after)}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["parts"] });
      setQty(""); setNote(""); setReference("");
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
        <Input label={type === "ADJUSTMENT" ? "Quantity (use − to reduce)" : "Quantity"} type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
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
                <p className="font-medium text-slate-800">{titleCase(t.transaction_type)}{t.job_card_number && ` · ${t.job_card_number}`}</p>
                <p className="truncate text-xs text-slate-500">{formatDateTime(t.created_at)}{t.created_by_name && ` · ${t.created_by_name}`}{t.note && ` · ${t.note}`}</p>
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

export function InventoryPage() {
  const { user } = useAuth();
  const canManage = user?.role === "AGENCY_ADMIN" || user?.role === "AGENCY_MANAGER";
  const [tab, setTab] = useState<"all" | "low">("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [moving, setMoving] = useState<Part | null>(null);
  const [editingPart, setEditingPart] = useState<Part | null>(null);
  const [ledger, setLedger] = useState<Part | null>(null);

  const query = useQuery({
    queryKey: ["parts", { tab, search, page }],
    queryFn: () => inventoryApi.list({ low_stock: tab === "low" ? true : undefined, search, page }),
    placeholderData: keepPreviousData,
  });
  const low = useQuery({ queryKey: ["parts", "low-count"], queryFn: () => inventoryApi.list({ low_stock: true, page_size: 1 }) });

  return (
    <>
      <PageHeader title="Inventory" description="Parts, stock levels and every stock movement."
        actions={canManage && <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> New part</Button>} />
      <div className="stagger mb-6 grid gap-4 sm:grid-cols-2">
        <StatsCard label="Parts tracked" value={query.data?.pagination.count ?? 0} icon={<ArrowDownUp className="h-5 w-5" />} />
        <StatsCard label="Below re-order level" value={low.data?.pagination.count ?? 0} icon={<AlertTriangle className="h-5 w-5" />} />
      </div>
      <Tabs items={[{ key: "all", label: "All parts" }, { key: "low", label: "Re-order list" }]} active={tab} onChange={(k) => { setTab(k); setPage(1); }} />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name, SKU, brand…" /></div>
        <DataTable<Part>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(p) => p.id}
          emptyTitle={tab === "low" ? "Nothing to re-order" : "No parts yet"}
          columns={[
            { key: "name", header: "Part", render: (p) => <div className="min-w-0"><p className="font-medium text-slate-900">{p.name}</p><p className="text-xs text-slate-500">{p.sku}{p.brand && ` · ${p.brand}`}</p></div> },
            {
              key: "stock", header: "Stock",
              render: (p) => <span className="whitespace-nowrap">{Number(p.stock_quantity)} {titleCase(p.unit)} {p.is_low_stock && <StatusBadge status="LOW_STOCK" label="Low" />}</span>,
            },
            { key: "sell", header: "Price", render: (p) => inr(p.selling_price), hideOnMobile: true },
            { key: "buy", header: "Cost", render: (p) => inr(p.purchase_price), hideOnMobile: true },
            {
              key: "actions", header: "", className: "text-right",
              render: (p) => (
                <div className="flex justify-end gap-1.5">
                  {canManage && <Button size="sm" variant="secondary" onClick={() => setEditingPart(p)}>Edit</Button>}
                  {canManage && <Button size="sm" variant="secondary" onClick={() => setMoving(p)}>Stock</Button>}
                  <Button size="sm" variant="ghost" aria-label="Ledger" onClick={() => setLedger(p)}><History className="h-4 w-4" /></Button>
                </div>
              ),
            },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
      <PartModal open={adding} onClose={() => setAdding(false)} />
      <PartModal open={Boolean(editingPart)} part={editingPart} onClose={() => setEditingPart(null)} />
      <MoveModal part={moving} onClose={() => setMoving(null)} />
      <LedgerModal part={ledger} onClose={() => setLedger(null)} />
    </>
  );
}
