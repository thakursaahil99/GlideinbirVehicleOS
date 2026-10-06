import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet, FileUp, XCircle } from "lucide-react";
import { useRef, useState } from "react";

import { ApiError, api, apiPost } from "@/api/client";
import { organizationsApi } from "@/api/resources";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/utils/format";

import { Button } from "./Button";
import { Select } from "./FormField";
import { Modal } from "./Modal";
import { useToast } from "./toast-context";

export type ImportResource = "parts" | "suppliers" | "categories" | "customers" | "vehicles";

interface ImportResult {
  dry_run: boolean;
  total_rows: number;
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; message: string }[];
  unknown_columns: string[];
}

const LABELS: Record<ImportResource, string> = {
  parts: "spare parts", suppliers: "suppliers", categories: "categories", customers: "customers", vehicles: "vehicles",
};

async function downloadTemplate(resource: ImportResource, format: "xlsx" | "csv") {
  const res = await api.get(`/imports/${resource}/template/`, { params: { file_format: format }, responseType: "blob" });
  const url = URL.createObjectURL(res.data as Blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: `${resource}-template.${format}` });
  a.click();
  URL.revokeObjectURL(url);
}

/** "Import" button + dialog: template → upload CSV / Excel / PDF → preview → import. */
export function ImportButton({ resource, invalidate }: { resource: ImportResource; invalidate: string[][] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}><FileUp className="h-4 w-4" /> Import</Button>
      {open && <ImportDialog resource={resource} invalidate={invalidate} onClose={() => setOpen(false)} />}
    </>
  );
}

function ImportDialog({ resource, invalidate, onClose }: { resource: ImportResource; invalidate: string[][]; onClose: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [organization, setOrganization] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragging, setDragging] = useState(false);
  const agencies = useQuery({
    queryKey: ["orgs", "import-picker"], queryFn: () => organizationsApi.list({ page_size: 100, status: "ACTIVE" }), enabled: isSuperAdmin,
  });

  const run = useMutation({
    mutationFn: (dryRun: boolean) => {
      const body = new FormData();
      body.append("file", file!);
      body.append("dry_run", String(dryRun));
      if (organization) body.append("organization", organization);
      return apiPost<ImportResult>(`/imports/${resource}/`, body, { timeout: 120_000 });
    },
    onSuccess: (r) => {
      setResult(r);
      if (!r.dry_run) {
        toast.show(`Imported: ${r.created} added, ${r.updated} updated${r.errors.length ? `, ${r.errors.length} rows skipped` : ""}.`, "success");
        invalidate.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
        onClose();
      }
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Import failed.", "error"),
  });

  const pick = (f: File | undefined | null) => { if (f) { setFile(f); setResult(null); } };
  const ready = Boolean(file) && (!isSuperAdmin || organization);
  const good = result ? result.created + result.updated : 0;

  return (
    <Modal open onClose={onClose} title={`Import ${LABELS[resource]}`}
      footer={<>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        {!result ? (
          <Button disabled={!ready} loading={run.isPending} onClick={() => run.mutate(true)}>Check file</Button>
        ) : (
          <Button disabled={good === 0} loading={run.isPending} onClick={() => run.mutate(false)}>Import {good} row{good === 1 ? "" : "s"}</Button>
        )}
      </>}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-600 ring-1 ring-slate-200/70">
          <FileSpreadsheet className="h-4 w-4 text-brand-600" />
          <span className="flex-1">Use our template so the columns match.</span>
          <Button size="sm" variant="secondary" onClick={() => downloadTemplate(resource, "xlsx")}><Download className="h-3.5 w-3.5" /> Excel</Button>
          <Button size="sm" variant="ghost" onClick={() => downloadTemplate(resource, "csv")}>CSV</Button>
        </div>

        {isSuperAdmin && (
          <Select label="Import into agency" value={organization} onChange={(e) => { setOrganization(e.target.value); setResult(null); }}>
            <option value="">Choose an agency…</option>
            {agencies.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        )}

        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
          className={cn(
            "flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition",
            dragging ? "border-brand-500 bg-brand-50" : "border-slate-300 hover:border-brand-400 hover:bg-slate-50",
          )}
        >
          <FileUp className={cn("h-8 w-8 transition", dragging ? "scale-110 text-brand-600" : "text-slate-400")} />
          <span className="text-sm font-medium text-slate-800">{file ? file.name : "Choose a file or drop it here"}</span>
          <span className="text-xs text-slate-500">CSV, Excel (.xlsx) or PDF with a table · max 5 MB, 2000 rows</span>
        </button>
        <input ref={input} type="file" className="hidden" accept=".csv,.xlsx,.xlsm,.pdf,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => pick(e.target.files?.[0])} />

        {result && (
          <div className="animate-fade-up space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl bg-emerald-50 p-3 ring-1 ring-emerald-200"><p className="font-display text-xl font-semibold text-emerald-700">{result.created}</p><p className="text-xs text-emerald-800">new</p></div>
              <div className="rounded-xl bg-sky-50 p-3 ring-1 ring-sky-200"><p className="font-display text-xl font-semibold text-sky-700">{result.updated}</p><p className="text-xs text-sky-800">updated</p></div>
              <div className="rounded-xl bg-rose-50 p-3 ring-1 ring-rose-200"><p className="font-display text-xl font-semibold text-rose-700">{result.errors.length}</p><p className="text-xs text-rose-800">with errors</p></div>
            </div>
            {result.skipped > 0 && <p className="text-xs text-slate-500">{result.skipped} row(s) already exist and will be skipped.</p>}
            {result.unknown_columns.length > 0 && <p className="text-xs text-amber-700">Ignored columns: {result.unknown_columns.join(", ")}</p>}
            {result.errors.length > 0 ? (
              <ul className="max-h-48 space-y-1 overflow-y-auto rounded-xl bg-rose-50/60 p-3 text-xs text-rose-800 ring-1 ring-rose-100">
                {result.errors.map((e) => <li key={e.row} className="flex gap-2"><XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span><b>Row {e.row}:</b> {e.message}</span></li>)}
              </ul>
            ) : (
              <p className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" /> All {result.total_rows} rows look good.</p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
