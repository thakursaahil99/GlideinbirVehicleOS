import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useEffect, useState } from "react";

import { staffApi, type StaffInput } from "@/api/agency";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Input, Select } from "@/components/ui/FormField";
import { ConfirmDialog, Modal } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Checkbox } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { StaffMember } from "@/types/api";
import { ROLE_LABELS, formatDateTime } from "@/utils/format";

const EMPTY: StaffInput = { email: "", full_name: "", phone: "", role: "AGENCY_STAFF", permissions: [] };

function StaffEditor({ member, open, onClose }: { member: StaffMember | null; open: boolean; onClose: () => void }) {
  const isNew = member === null;
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<StaffInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const codes = useQuery({ queryKey: ["permission-codes"], queryFn: staffApi.permissionCodes, staleTime: Infinity });

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(member ? { full_name: member.full_name, phone: member.phone, role: member.role, permissions: member.permissions } : EMPTY);
  }, [open, member]);

  const save = useMutation({
    mutationFn: () => {
      if (isNew) {
        // Leave permissions undefined to apply the role's defaults when none were picked.
        const { permissions, ...rest } = form;
        return staffApi.create(permissions && permissions.length ? form : rest);
      }
      return staffApi.update(member.id, { full_name: form.full_name, phone: form.phone, role: form.role, permissions: form.permissions });
    },
    onSuccess: (m) => {
      toast.show(isNew ? `Invitation sent to ${m.email}.` : "Staff member updated.", "success");
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });

  const togglePerm = (code: string, on: boolean) =>
    setForm((f) => ({ ...f, permissions: on ? [...(f.permissions ?? []), code] : (f.permissions ?? []).filter((c) => c !== code) }));

  return (
    <Modal
      open={open}
      title={isNew ? "Add staff member" : `Edit ${member.full_name}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>{isNew ? "Send invite" : "Save"}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {isNew && (
          <Input label="E-mail" type="email" value={form.email} error={errors.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} hint="They'll receive a link to set their password." />
        )}
        <Input label="Full name" value={form.full_name} error={errors.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <Input label="Phone" type="tel" value={form.phone} error={errors.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <Select label="Role" value={form.role} error={errors.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="AGENCY_MANAGER">Manager</option>
          <option value="AGENCY_STAFF">Staff</option>
        </Select>
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-700">Permissions</legend>
          {isNew && <p className="mb-2 text-xs text-slate-500">Leave empty to use the role's default permissions.</p>}
          <div className="grid gap-2 sm:grid-cols-2">
            {codes.data?.map((c) => (
              <Checkbox key={c.code} label={c.label} checked={form.permissions?.includes(c.code) ?? false} onChange={(on) => togglePerm(c.code, on)} />
            ))}
          </div>
        </fieldset>
      </div>
    </Modal>
  );
}

export function AgencyStaffPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "AGENCY_ADMIN";
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<StaffMember | null | undefined>(undefined);
  const [toggling, setToggling] = useState<StaffMember | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["staff", { search, page }],
    queryFn: () => staffApi.list({ search, page }),
    placeholderData: keepPreviousData,
  });

  const toggle = useMutation({
    mutationFn: (m: StaffMember) => (m.is_active ? staffApi.deactivate(m.id) : staffApi.activate(m.id)),
    onSuccess: (m) => {
      toast.show(`${m.full_name} is now ${m.is_active ? "active" : "deactivated"}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      setToggling(null);
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error"),
  });

  const canManage = (m: StaffMember) => isAdmin && m.role !== "AGENCY_ADMIN" && m.user_id !== user?.id;

  return (
    <>
      <PageHeader
        title="Staff"
        description="Managers and technicians with access to your agency."
        actions={isAdmin && <Button onClick={() => setEditing(null)}><UserPlus className="h-4 w-4" /> Add member</Button>}
      />
      <Card>
        <div className="mb-4"><SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search name, e-mail, phone…" /></div>
        <DataTable<StaffMember>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(m) => m.id}
          columns={[
            {
              key: "user",
              header: "Member",
              render: (m) => (
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{m.full_name}</p>
                  <p className="truncate text-xs text-slate-500">{m.email}</p>
                </div>
              ),
            },
            { key: "role", header: "Role", render: (m) => ROLE_LABELS[m.role] },
            { key: "perms", header: "Permissions", hideOnMobile: true, render: (m) => (m.role === "AGENCY_ADMIN" ? "All" : `${m.permissions.length} granted`) },
            { key: "login", header: "Last login", hideOnMobile: true, render: (m) => formatDateTime(m.last_login) },
            { key: "status", header: "Status", render: (m) => <StatusBadge status={m.is_active ? "ACTIVE" : "INACTIVE"} /> },
            {
              key: "actions",
              header: "",
              className: "text-right",
              render: (m) =>
                canManage(m) && (
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" variant="secondary" onClick={() => setEditing(m)}>Edit</Button>
                    <Button size="sm" variant={m.is_active ? "ghost" : "success"} onClick={() => setToggling(m)}>
                      {m.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </div>
                ),
            },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>

      <StaffEditor member={editing ?? null} open={editing !== undefined} onClose={() => setEditing(undefined)} />
      <ConfirmDialog
        open={Boolean(toggling)}
        title={toggling?.is_active ? "Deactivate staff member?" : "Activate staff member?"}
        message={toggling?.is_active ? `${toggling.full_name} will be signed out and lose access.` : `${toggling?.full_name} will regain access.`}
        confirmLabel={toggling?.is_active ? "Deactivate" : "Activate"}
        tone={toggling?.is_active ? "danger" : "success"}
        loading={toggle.isPending}
        onCancel={() => setToggling(null)}
        onConfirm={() => toggling && toggle.mutate(toggling)}
      />
    </>
  );
}
