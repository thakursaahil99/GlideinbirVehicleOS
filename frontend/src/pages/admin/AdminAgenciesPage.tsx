import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, UserPlus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { ApiError } from "@/api/client";
import { organizationsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/FormField";
import { ConfirmDialog } from "@/components/ui/Modal";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/toast-context";
import type { Organization, OrganizationStatus, StatusAction } from "@/types/api";
import { formatDate } from "@/utils/format";

import { CreateAgencyModal } from "./CreateAgencyModal";
import { CreateUserModal } from "./CreateUserModal";
import { EditAgencyModal } from "./EditModals";

const ACTIONS: Record<StatusAction, { label: string; tone: "primary" | "danger" | "success"; from: OrganizationStatus[]; reason: boolean }> = {
  approve: { label: "Approve", tone: "success", from: ["PENDING", "REJECTED"], reason: false },
  reject: { label: "Reject", tone: "danger", from: ["PENDING"], reason: true },
  suspend: { label: "Suspend", tone: "danger", from: ["ACTIVE", "INACTIVE"], reason: true },
  reactivate: { label: "Reactivate", tone: "success", from: ["SUSPENDED", "INACTIVE"], reason: false },
  deactivate: { label: "Deactivate", tone: "primary", from: ["ACTIVE"], reason: false },
};

const STATUSES: OrganizationStatus[] = ["PENDING", "ACTIVE", "INACTIVE", "SUSPENDED", "REJECTED"];

export function AdminAgenciesPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const search = params.get("search") ?? "";
  const page = Number(params.get("page") ?? 1);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Organization | null>(null);
  const [addingTo, setAddingTo] = useState<string | undefined>(undefined);
  const [pendingAction, setPendingAction] = useState<{ org: Organization; action: StatusAction } | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const query = useQuery({
    queryKey: ["orgs", "list", { status, search, page }],
    queryFn: () => organizationsApi.list({ status, search, page, ordering: "-created_at" }),
    placeholderData: keepPreviousData,
  });

  const mutation = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: StatusAction; reason: string }) =>
      organizationsApi.changeStatus(id, action, reason),
    onSuccess: (org, { action }) => {
      toast.show(`${org.name}: ${ACTIONS[action].label.toLowerCase()} successful.`, "success");
      queryClient.invalidateQueries({ queryKey: ["orgs"] });
      setPendingAction(null);
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Action failed.", "error"),
  });

  return (
    <>
      <PageHeader
        title="Agencies"
        description="Create, approve, suspend and reactivate agencies on the platform."
        actions={<Button onClick={() => setCreating(true)}><Building2 className="h-4 w-4" /> New agency</Button>}
      />
      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <SearchBar value={search} onChange={(v) => setParam("search", v)} placeholder="Search name, e-mail, phone, GSTIN…" />
          <Select aria-label="Filter by status" value={status} onChange={(e) => setParam("status", e.target.value)} wrapperClassName="sm:w-48">
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0) + s.slice(1).toLowerCase()}
              </option>
            ))}
          </Select>
        </div>
        <DataTable<Organization>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(o) => o.id}
          emptyTitle="No agencies match these filters"
          columns={[
            {
              key: "name",
              header: "Agency",
              render: (o) => (
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{o.name}</p>
                  <p className="truncate text-xs text-slate-500">{o.email}</p>
                </div>
              ),
            },
            { key: "city", header: "City", render: (o) => o.city, hideOnMobile: true },
            { key: "members", header: "Members", render: (o) => o.member_count ?? "—", hideOnMobile: true },
            { key: "created", header: "Registered", render: (o) => formatDate(o.created_at), hideOnMobile: true },
            {
              key: "status",
              header: "Status",
              render: (o) => (
                <div className="space-y-1">
                  <StatusBadge status={o.status} />
                  {o.status_reason && <p className="max-w-[16rem] truncate text-xs text-slate-500" title={o.status_reason}>{o.status_reason}</p>}
                </div>
              ),
            },
            {
              key: "actions",
              header: "",
              className: "text-right",
              render: (o) => (
                <div className="flex flex-wrap justify-end gap-1.5">
                  <Button size="sm" variant="secondary" onClick={() => setEditing(o)}>Edit</Button>
                  <Button size="sm" variant="secondary" onClick={() => setAddingTo(o.id)} aria-label={`Add user to ${o.name}`}>
                    <UserPlus className="h-3.5 w-3.5" /> Add user
                  </Button>
                  {(Object.keys(ACTIONS) as StatusAction[])
                    .filter((a) => ACTIONS[a].from.includes(o.status))
                    .map((a) => (
                      <Button key={a} size="sm" variant={ACTIONS[a].tone === "primary" ? "secondary" : ACTIONS[a].tone} onClick={() => setPendingAction({ org: o, action: a })}>
                        {ACTIONS[a].label}
                      </Button>
                    ))}
                </div>
              ),
            },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={(p) => setParam("page", String(p))} />
      </Card>

      <CreateAgencyModal open={creating} onClose={() => setCreating(false)} />
      <EditAgencyModal org={editing} onClose={() => setEditing(null)} />
      <CreateUserModal open={Boolean(addingTo)} defaultOrganization={addingTo} onClose={() => setAddingTo(undefined)} />
      <ConfirmDialog
        open={Boolean(pendingAction)}
        title={pendingAction ? `${ACTIONS[pendingAction.action].label} ${pendingAction.org.name}?` : ""}
        message={
          pendingAction?.action === "suspend"
            ? "Suspended agencies cannot receive new bookings until reactivated."
            : "This change is recorded in the audit log."
        }
        confirmLabel={pendingAction ? ACTIONS[pendingAction.action].label : "Confirm"}
        tone={pendingAction ? ACTIONS[pendingAction.action].tone : "primary"}
        withReason
        reasonRequired={pendingAction ? ACTIONS[pendingAction.action].reason : false}
        loading={mutation.isPending}
        onCancel={() => setPendingAction(null)}
        onConfirm={(reason) => pendingAction && mutation.mutate({ id: pendingAction.org.id, action: pendingAction.action, reason })}
      />
    </>
  );
}
