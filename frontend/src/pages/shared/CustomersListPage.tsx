import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { customersApi } from "@/api/customers";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { ImportButton } from "@/components/ui/ImportButton";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { Customer } from "@/types/api";
import { formatDate } from "@/utils/format";

function WalkInModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ full_name: "", phone: "", email: "", city: "", address: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => customersApi.create(form),
    onSuccess: () => {
      toast.show("Customer added.", "success");
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      setForm({ full_name: "", phone: "", email: "", city: "", address: "" });
      onClose();
    },
    onError: (err) => err instanceof ApiError && (setErrors(err.fieldErrors()), toast.show(err.message, "error")),
  });
  const bind = (k: keyof typeof form) => ({ value: form[k], error: errors[k], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value }) });
  return (
    <Modal open={open} onClose={onClose} title="Add walk-in customer"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={create.isPending} onClick={() => create.mutate()}>Add customer</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Full name" {...bind("full_name")} />
        <Input label="Phone" type="tel" placeholder="+919876543210" {...bind("phone")} />
        <Input label="E-mail (optional)" type="email" {...bind("email")} />
        <Input label="City" {...bind("city")} />
        <Textarea label="Address" wrapperClassName="sm:col-span-2" {...bind("address")} />
      </div>
    </Modal>
  );
}

/** Agency: customers linked to the agency. Super Admin: every customer. */
export function CustomersListPage({ basePath }: { basePath: string }) {
  const { user } = useAuth();
  const canCreate = Boolean(user?.organization) && user!.permissions.includes("CUSTOMER_CREATE");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const query = useQuery({
    queryKey: ["customers", { search, page }],
    queryFn: () => customersApi.list({ search, page }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader title="Customers"
        description={user?.role === "SUPER_ADMIN" ? "Every customer on the platform." : "Customers who booked with you or were added by your team."}
        actions={canCreate && <div className="flex flex-wrap gap-2"><ImportButton resource="customers" invalidate={[["customers"]]} /><Button onClick={() => setAdding(true)}><UserPlus className="h-4 w-4" /> Add walk-in</Button></div>} />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name, phone, e-mail, registration no…" /></div>
        <DataTable<Customer>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(c) => c.id}
          emptyTitle="No customers yet"
          columns={[
            {
              key: "name", header: "Customer",
              render: (c) => (
                <Link to={`${basePath}/${c.id}`} className="block min-w-0 hover:underline">
                  <span className="font-medium text-slate-900">{c.full_name}</span>
                  <span className="block truncate text-xs text-slate-500">{c.email || c.phone}</span>
                </Link>
              ),
            },
            { key: "phone", header: "Phone", render: (c) => c.phone || "—", hideOnMobile: true },
            { key: "city", header: "City", render: (c) => c.city || "—", hideOnMobile: true },
            { key: "vehicles", header: "Vehicles", render: (c) => c.vehicle_count ?? 0 },
            { key: "type", header: "Type", render: (c) => <StatusBadge status={c.has_account ? "ACTIVE" : "INACTIVE"} label={c.has_account ? "App user" : "Walk-in"} /> },
            { key: "since", header: "Since", render: (c) => formatDate(c.created_at), hideOnMobile: true },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
      <WalkInModal open={adding} onClose={() => setAdding(false)} />
    </>
  );
}
