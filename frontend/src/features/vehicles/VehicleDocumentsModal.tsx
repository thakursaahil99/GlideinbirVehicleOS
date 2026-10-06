import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { vehiclesApi } from "@/api/customers";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Card";
import { Select } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import type { Vehicle } from "@/types/api";
import { formatDate } from "@/utils/format";

const KINDS = { RC: "Registration certificate", INSURANCE: "Insurance", PUC: "Pollution certificate", PHOTO: "Photo", OTHER: "Other" };

export function VehicleDocumentsModal({ vehicle, onClose }: { vehicle: Vehicle | null; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState("RC");
  const docs = useQuery({
    queryKey: ["vehicles", vehicle?.id, "documents"],
    queryFn: () => vehiclesApi.documents(vehicle!.id),
    enabled: Boolean(vehicle),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["vehicles", vehicle?.id, "documents"] });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      return vehiclesApi.uploadDocument(vehicle!.id, form);
    },
    onSuccess: () => { toast.show("Document uploaded.", "success"); refresh(); },
    onError: (err) => toast.show(err instanceof ApiError ? Object.values(err.fieldErrors())[0] ?? err.message : "Upload failed.", "error"),
  });
  const remove = useMutation({
    mutationFn: (docId: string) => vehiclesApi.deleteDocument(vehicle!.id, docId),
    onSuccess: refresh,
  });

  return (
    <Modal open={Boolean(vehicle)} onClose={onClose} title={vehicle ? `Documents · ${vehicle.registration_number}` : ""}>
      {vehicle?.can_edit && (
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end">
          <Select label="Document type" value={kind} onChange={(e) => setKind(e.target.value)} wrapperClassName="flex-1">
            {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
          <Button loading={upload.isPending} onClick={() => fileRef.current?.click()}>Upload file</Button>
        </div>
      )}
      <p className="mb-3 text-xs text-slate-500">PDF, JPG, PNG or WEBP up to 10 MB.</p>
      {docs.isLoading ? <Spinner /> : (
        <ul className="divide-y divide-slate-100">
          {docs.data?.length === 0 && <li className="py-4 text-sm text-slate-500">No documents yet.</li>}
          {docs.data?.map((d) => (
            <li key={d.id} className="flex items-center gap-3 py-2.5">
              <FileText className="h-4 w-4 text-slate-400" />
              <a href={d.file} target="_blank" rel="noreferrer" className="flex-1 truncate text-sm font-medium text-brand-700 hover:underline">
                {KINDS[d.kind]}
              </a>
              <span className="text-xs text-slate-500">{formatDate(d.created_at)}</span>
              {vehicle?.can_edit && (
                <button type="button" aria-label="Delete document" onClick={() => remove.mutate(d.id)} className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600">
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
