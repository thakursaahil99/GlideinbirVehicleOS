import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CreditCard, Download, Receipt, Smartphone, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "@/api/client";
import { invoicesApi, paymentsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Alert, Card, PageHeader, Skeleton } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { Payment } from "@/types/operations";
import { formatDate, formatDateTime, inr, titleCase } from "@/utils/format";

function RecordPaymentModal({ invoiceId, balance, open, onClose }: { invoiceId: string; balance: string; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState(balance);
  const [method, setMethod] = useState("CASH");
  const [reference, setReference] = useState("");
  const record = useMutation({
    mutationFn: () => paymentsApi.record({ invoice: invoiceId, amount, method, reference }),
    onSuccess: () => { toast.show("Payment recorded.", "success"); queryClient.invalidateQueries({ queryKey: ["invoices"] }); queryClient.invalidateQueries({ queryKey: ["payments"] }); onClose(); },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not record payment.", "error"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Record a payment"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={record.isPending} onClick={() => record.mutate()}>Record</Button></>}>
      <div className="space-y-4">
        <Input label="Amount (₹)" type="number" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} hint={`Balance due ${inr(balance)}`} />
        <Select label="Method" value={method} onChange={(e) => setMethod(e.target.value)}>
          <option value="CASH">Cash</option>
          <option value="BANK_TRANSFER">Bank transfer</option>
        </Select>
        <Input label="Reference (receipt / UTR)" value={reference} onChange={(e) => setReference(e.target.value)} />
      </div>
    </Modal>
  );
}

export function InvoiceDetailPage({ backTo }: { backTo: string }) {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const isAdmin = user?.role === "AGENCY_ADMIN";
  const canEdit = isAdmin || user?.role === "AGENCY_MANAGER";
  const toast = useToast();
  const queryClient = useQueryClient();
  const [recording, setRecording] = useState(false);
  const [voiding, setVoiding] = useState(false);
  const [refunding, setRefunding] = useState<Payment | null>(null);
  const [discount, setDiscount] = useState<string | null>(null);

  const invoice = useQuery({ queryKey: ["invoices", id], queryFn: () => invoicesApi.get(id) });
  const payments = useQuery({ queryKey: ["payments", "invoice", id], queryFn: () => paymentsApi.list({ invoice: id, page_size: 50 }) });
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ["invoices"] }); queryClient.invalidateQueries({ queryKey: ["payments"] }); };
  const onError = (err: unknown) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error");

  const pay = useMutation({
    mutationFn: (method: string) => paymentsApi.pay({ invoice: id, method, idempotency_key: `${id}-${Date.now()}` }),
    onSuccess: (p) => { refresh(); toast.show(p.status === "SUCCEEDED" ? "Payment successful. Thank you!" : p.failure_reason || "Payment failed.", p.status === "SUCCEEDED" ? "success" : "error"); },
    onError,
  });
  const download = useMutation({ mutationFn: () => invoicesApi.downloadPdf(id, `${invoice.data?.invoice_number}.pdf`), onError });
  const voidInvoice = useMutation({ mutationFn: (reason: string) => invoicesApi.void(id, reason), onSuccess: () => { refresh(); setVoiding(false); }, onError });
  const saveDiscount = useMutation({ mutationFn: () => invoicesApi.update(id, { discount: discount ?? "0" }), onSuccess: () => { refresh(); setDiscount(null); toast.show("Invoice updated.", "success"); }, onError });
  const refund = useMutation({
    mutationFn: (reason: string) => paymentsApi.refund(refunding!.id, undefined, reason),
    onSuccess: () => { refresh(); setRefunding(null); toast.show("Refund processed.", "success"); },
    onError,
  });

  if (invoice.isLoading) return <Skeleton rows={6} />;
  if (!invoice.data) return <Alert tone="danger">Invoice not found.</Alert>;
  const inv = invoice.data;
  const due = Number(inv.balance_due) > 0 && inv.status === "ISSUED";

  return (
    <>
      <Link to={backTo} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="h-4 w-4" /> Invoices</Link>
      <PageHeader title={inv.invoice_number} description={`${inv.organization_name} · ${formatDate(inv.invoice_date)}${inv.booking_number ? ` · ${inv.booking_number}` : ""}`}
        actions={<StatusBadge status={inv.status === "VOID" ? "VOID" : inv.payment_status} label={inv.status === "VOID" ? "Void" : titleCase(inv.payment_status)} />} />
      {inv.status === "VOID" && <div className="mb-4"><Alert tone="danger">Voided — {inv.void_reason}</Alert></div>}

      <div className="stagger mb-6 flex flex-wrap gap-2">
        {inv.status !== "VOID" && <Button variant="secondary" loading={download.isPending} onClick={() => download.mutate()}><Download className="h-4 w-4" /> Download PDF</Button>}
        {!isCustomer && due && <Button onClick={() => setRecording(true)}><Receipt className="h-4 w-4" /> Record payment</Button>}
        {canEdit && inv.status === "ISSUED" && Number(inv.amount_paid) === 0 && <Button variant="ghost" onClick={() => setVoiding(true)}>Void</Button>}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Items" className="lg:col-span-2">
          <ul className="divide-y divide-slate-100 text-sm">
            {inv.items?.map((it) => (
              <li key={it.id} className="flex items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-900">{it.description}</p>
                  <p className="text-xs text-slate-500">{Number(it.quantity)} × {inr(it.unit_price)} · GST {Number(it.tax_rate)}% ({inr(it.tax_amount)})</p>
                </div>
                <span className="font-medium">{inr(it.total)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-4 space-y-1.5 border-t border-slate-100 pt-4 text-sm">
            <div className="flex justify-between"><dt className="text-slate-500">Subtotal</dt><dd>{inr(inv.subtotal)}</dd></div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-slate-500">Discount</dt>
              <dd className="flex items-center gap-2">
                {canEdit && inv.status === "ISSUED" && Number(inv.amount_paid) === 0 ? (
                  <>
                    <input aria-label="Discount" type="number" inputMode="decimal" value={discount ?? inv.discount} onChange={(e) => setDiscount(e.target.value)}
                      className="w-28 rounded-lg border-0 px-2 py-1 text-right text-base ring-1 ring-slate-200 focus:ring-2 focus:ring-brand-500 sm:text-sm" />
                    {discount !== null && <Button size="sm" loading={saveDiscount.isPending} onClick={() => saveDiscount.mutate()}>Apply</Button>}
                  </>
                ) : <>− {inr(inv.discount)}</>}
              </dd>
            </div>
            <div className="flex justify-between"><dt className="text-slate-500">GST</dt><dd>{inr(inv.tax)}</dd></div>
            <div className="flex justify-between font-display text-lg font-semibold text-brand-700"><dt>Total</dt><dd>{inr(inv.total)}</dd></div>
            <div className="flex justify-between text-slate-600"><dt>Paid</dt><dd>{inr(inv.amount_paid)}</dd></div>
            <div className="flex justify-between font-semibold"><dt>Balance due</dt><dd>{inr(inv.balance_due)}</dd></div>
          </dl>
        </Card>

        <div className="space-y-6">
          {isCustomer && due && (
            <Card title="Pay now">
              <div className="space-y-2">
                <Button className="w-full" loading={pay.isPending} onClick={() => pay.mutate("UPI")}><Smartphone className="h-4 w-4" /> Pay {inr(inv.balance_due)} via UPI</Button>
                <Button className="w-full" variant="secondary" loading={pay.isPending} onClick={() => pay.mutate("CARD")}><CreditCard className="h-4 w-4" /> Pay by card</Button>
              </div>
              <p className="mt-3 text-xs text-slate-500">Development mode uses a mock gateway — no real money moves.</p>
            </Card>
          )}
          <Card title="Payments">
            {payments.data?.items.length ? (
              <ul className="space-y-3 text-sm">
                {payments.data.items.map((p) => (
                  <li key={p.id} className="rounded-xl bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{inr(p.amount)} · {titleCase(p.method)}</span>
                      <StatusBadge status={p.status} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{formatDateTime(p.paid_at ?? p.created_at)}{p.reference && ` · ${p.reference}`}</p>
                    {Number(p.refunded_amount) > 0 && <p className="text-xs text-rose-600">Refunded {inr(p.refunded_amount)}</p>}
                    {p.failure_reason && <p className="text-xs text-rose-600">{p.failure_reason}</p>}
                    {isAdmin && ["SUCCEEDED", "PARTIALLY_REFUNDED"].includes(p.status) && (
                      <Button size="sm" variant="ghost" className="mt-1" onClick={() => setRefunding(p)}><Undo2 className="h-3.5 w-3.5" /> Refund</Button>
                    )}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">No payments yet.</p>}
          </Card>
        </div>
      </div>

      {recording && <RecordPaymentModal invoiceId={id} balance={inv.balance_due} open onClose={() => setRecording(false)} />}
      <ConfirmDialog open={voiding} title="Void this invoice?" tone="danger" confirmLabel="Void" withReason reasonRequired
        message="Voided invoices stay on record but can't be paid." loading={voidInvoice.isPending}
        onCancel={() => setVoiding(false)} onConfirm={(r) => voidInvoice.mutate(r)} />
      <ConfirmDialog open={Boolean(refunding)} title={refunding ? `Refund ${inr(Number(refunding.amount) - Number(refunding.refunded_amount))}?` : ""} tone="danger"
        confirmLabel="Refund" withReason reasonRequired message="The full remaining amount goes back via the original method."
        loading={refund.isPending} onCancel={() => setRefunding(null)} onConfirm={(r) => refund.mutate(r)} />
    </>
  );
}
