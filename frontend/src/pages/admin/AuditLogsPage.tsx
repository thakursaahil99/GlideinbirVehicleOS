import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { auditLogsApi } from "@/api/resources";
import { Card, PageHeader } from "@/components/ui/Card";
import { DataTable, Pagination } from "@/components/ui/DataTable";
import { SearchBar } from "@/components/ui/SearchBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import type { AuditLog } from "@/types/api";
import { formatDateTime } from "@/utils/format";

function Changes({ log }: { log: AuditLog }) {
  const keys = Array.from(new Set([...Object.keys(log.old_data ?? {}), ...Object.keys(log.new_data ?? {})]));
  if (keys.length === 0) return <span className="text-slate-400">—</span>;
  return (
    <ul className="space-y-0.5 text-xs">
      {keys.slice(0, 4).map((k) => (
        <li key={k} className="truncate">
          <span className="font-medium text-slate-600">{k}</span>:{" "}
          {log.old_data && k in log.old_data && <span className="text-rose-600 line-through">{String(log.old_data[k])}</span>}{" "}
          {log.new_data && k in log.new_data && <span className="text-emerald-700">{String(log.new_data[k])}</span>}
        </li>
      ))}
    </ul>
  );
}

/** Shared by Super Admin (all tenants) and Agency Admin (own tenant — scoped by the backend). */
export function AuditLogsPage() {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["audit-logs", { search, page }],
    queryFn: () => auditLogsApi.list({ search, page }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Audit logs"
        description={user?.role === "SUPER_ADMIN" ? "Immutable record of sensitive actions across the platform." : "Immutable record of sensitive actions in your agency."}
      />
      <Card>
        <div className="mb-4">
          <SearchBar value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search model, object id, e-mail…" />
        </div>
        <DataTable<AuditLog>
          rows={query.data?.items}
          loading={query.isFetching}
          rowKey={(l) => l.id}
          columns={[
            { key: "when", header: "When", render: (l) => <span className="whitespace-nowrap">{formatDateTime(l.created_at)}</span> },
            { key: "action", header: "Action", render: (l) => <StatusBadge status={l.action} /> },
            { key: "who", header: "User", render: (l) => l.user_email ?? "—", hideOnMobile: true },
            ...(user?.role === "SUPER_ADMIN"
              ? [{ key: "org", header: "Agency", render: (l: AuditLog) => l.organization_name ?? "—", hideOnMobile: true }]
              : []),
            { key: "changes", header: "Changes", render: (l) => <Changes log={l} />, hideOnMobile: true },
            { key: "ip", header: "IP", render: (l) => l.ip_address ?? "—", hideOnMobile: true },
          ]}
        />
        <Pagination meta={query.data?.pagination} onPageChange={setPage} />
      </Card>
    </>
  );
}
