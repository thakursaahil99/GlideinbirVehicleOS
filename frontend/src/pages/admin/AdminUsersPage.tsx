import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { usersApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/FormField";
import { ConfirmDialog } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";
import type { Role, User } from "@/types/api";
import { ROLE_LABELS, formatDateTime } from "@/utils/format";

import { CreateUserModal } from "./CreateUserModal";

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<User | null>(null);
  const [creating, setCreating] = useState(false);
  const toast = useToast();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["users", "list", { role, search, page }],
    queryFn: () => usersApi.list({ role, search, page }),
    placeholderData: keepPreviousData,
  });

  const mutation = useMutation({
    mutationFn: (u: User) => (u.is_active ? usersApi.deactivate(u.id) : usersApi.activate(u.id)),
    onSuccess: (u) => {
      toast.show(`${u.email} is now ${u.is_active ? "active" : "deactivated"}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setTarget(null);
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error"),
  });

  return (
    <>
      <PageHeader
        title="Users"
        description="Every account on the platform. Deactivating a user revokes their sessions."
        actions={<Button onClick={() => setCreating(true)}><UserPlus className="h-4 w-4" /> New user</Button>}
      />
      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search name, e-mail, phone…" />
          <Select aria-label="Filter by role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} wrapperClassName="sm:w-48">
            <option value="">All roles</option>
            {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
            ))}
          </Select>
        </div>
        <DataTable<User>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(u) => u.id}
          columns={[
            {
              key: "user",
              header: "User",
              render: (u) => (
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{u.full_name}</p>
                  <p className="truncate text-xs text-slate-500">{u.email}</p>
                </div>
              ),
            },
            { key: "role", header: "Role", render: (u) => ROLE_LABELS[u.role] },
            { key: "org", header: "Agency", render: (u) => u.organization?.name ?? "—", hideOnMobile: true },
            { key: "login", header: "Last login", render: (u) => formatDateTime(u.last_login), hideOnMobile: true },
            { key: "status", header: "Status", render: (u) => <StatusBadge status={u.is_active ? "ACTIVE" : "INACTIVE"} /> },
            {
              key: "actions",
              header: "",
              className: "text-right",
              render: (u) =>
                u.id === me?.id ? null : (
                  <Button size="sm" variant={u.is_active ? "secondary" : "success"} onClick={() => setTarget(u)}>
                    {u.is_active ? "Deactivate" : "Activate"}
                  </Button>
                ),
            },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
      <CreateUserModal open={creating} onClose={() => setCreating(false)} />
      <ConfirmDialog
        open={Boolean(target)}
        title={target?.is_active ? "Deactivate user?" : "Activate user?"}
        message={target?.is_active ? `${target.email} will be signed out and unable to log in.` : `${target?.email} will be able to log in again.`}
        confirmLabel={target?.is_active ? "Deactivate" : "Activate"}
        tone={target?.is_active ? "danger" : "success"}
        loading={mutation.isPending}
        onCancel={() => setTarget(null)}
        onConfirm={() => target && mutation.mutate(target)}
      />
    </>
  );
}
