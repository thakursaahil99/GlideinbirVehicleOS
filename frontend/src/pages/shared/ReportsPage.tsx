import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { FileSpreadsheet, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { reportsApi } from "@/api/operations";
import { organizationsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Alert, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/Card";
import { Select } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/toast-context";
import { DateRangeFilter, defaultRange } from "@/features/dashboard/DateRangeFilter";
import { useAuth } from "@/hooks/useAuth";
import { cn, titleCase } from "@/utils/format";

const MONEY_COLUMNS = /revenue|total|paid|balance/;

function formatCell(column: string, value: unknown) {
  if (value === null || value === undefined) return "—";
  if (MONEY_COLUMNS.test(column) && !Number.isNaN(Number(value))) return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  if (column.endsWith("_pct") || column === "rate") return `${value}%`;
  return String(value);
}

export function ReportsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "SUPER_ADMIN";
  const toast = useToast();
  const [name, setName] = useState<string>("");
  const [range, setRange] = useState(defaultRange);
  const [organization, setOrganization] = useState("");

  const catalog = useQuery({ queryKey: ["reports", "catalog"], queryFn: reportsApi.catalog });
  const agencies = useQuery({ queryKey: ["orgs", "all"], queryFn: () => organizationsApi.list({ page_size: 100 }), enabled: isAdmin });
  useEffect(() => { if (!name && catalog.data?.length) setName(catalog.data[0].name); }, [catalog.data, name]);

  const params = { ...range, organization };
  const report = useQuery({
    queryKey: ["reports", name, params],
    queryFn: () => reportsApi.run(name, params),
    enabled: Boolean(name),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const download = useMutation({
    mutationFn: (format: "csv" | "xlsx") => reportsApi.download(name, format, params),
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Export failed.", "error"),
  });

  if (catalog.isError) return <Alert tone="danger">{catalog.error instanceof ApiError ? catalog.error.message : "Reports unavailable."}</Alert>;

  return (
    <>
      <PageHeader title="Reports" description="Run, preview and export to CSV or Excel."
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" disabled={!name} loading={download.isPending && download.variables === "csv"} onClick={() => download.mutate("csv")}><FileText className="h-4 w-4" /> CSV</Button>
            <Button variant="secondary" disabled={!name} loading={download.isPending && download.variables === "xlsx"} onClick={() => download.mutate("xlsx")}><FileSpreadsheet className="h-4 w-4" /> Excel</Button>
          </div>
        } />
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <Card title="Report">
          {catalog.isLoading ? <Skeleton rows={4} /> : (
            <>
              <div className="lg:hidden">
                <Select aria-label="Report" value={name} onChange={(e) => setName(e.target.value)}>
                  {catalog.data?.map((r) => <option key={r.name} value={r.name}>{r.title}</option>)}
                </Select>
              </div>
              <ul className="hidden space-y-1 lg:block">
                {catalog.data?.map((r) => (
                  <li key={r.name}>
                    <button type="button" onClick={() => setName(r.name)}
                      className={cn("w-full rounded-xl px-3 py-2 text-left text-sm transition", name === r.name ? "bg-brand-50 font-medium text-brand-700" : "text-slate-600 hover:bg-slate-50")}>
                      {r.title}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <div className="min-w-0 space-y-4">
          <Card>
            <div className="flex flex-col gap-3 md:flex-row md:items-end">
              <DateRangeFilter value={range} onChange={setRange} />
              {isAdmin && (
                <Select aria-label="Agency" value={organization} onChange={(e) => setOrganization(e.target.value)} wrapperClassName="md:w-56">
                  <option value="">All agencies</option>
                  {agencies.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </Select>
              )}
            </div>
          </Card>
          <Card title={report.data?.title}>
            {report.isError ? <Alert tone="warning">{report.error instanceof ApiError ? report.error.message : "Could not run report."}</Alert>
              : report.isLoading ? <Skeleton rows={5} />
                : !report.data?.rows.length ? <EmptyState title="No data for this period" />
                  : (
                    <div className="-mx-4 overflow-x-auto sm:-mx-5">
                      <table className="min-w-full divide-y divide-slate-200 text-sm">
                        <thead className="bg-slate-50/80">
                          <tr>{report.data.columns.map((c) => <th key={c} className="whitespace-nowrap px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 sm:px-5">{titleCase(c)}</th>)}</tr>
                        </thead>
                        <tbody className="stagger divide-y divide-slate-100">
                          {report.data.rows.map((row, i) => (
                            <tr key={i} className="hover:bg-brand-50/40">
                              {report.data.columns.map((c) => <td key={c} className="whitespace-nowrap px-4 py-2.5 text-slate-700 sm:px-5">{formatCell(c, row[c])}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
          </Card>
        </div>
      </div>
    </>
  );
}
