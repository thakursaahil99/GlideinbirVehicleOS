import { useQuery } from "@tanstack/react-query";
import { Building2, Car, ClipboardList, Contact, FileText, Search, Ticket } from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";
import { Link, useSearchParams } from "react-router";

import { reportsApi } from "@/api/operations";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import type { SearchResults } from "@/types/operations";
import { titleCase } from "@/utils/format";

const GROUPS: { key: keyof SearchResults; label: string; icon: ComponentType<{ className?: string }>; path: (area: string) => string | null }[] = [
  { key: "bookings", label: "Bookings", icon: Ticket, path: (a) => `/${a}/bookings` },
  { key: "customers", label: "Customers", icon: Contact, path: (a) => (a === "customer" ? null : `/${a}/customers`) },
  { key: "vehicles", label: "Vehicles", icon: Car, path: () => null },
  { key: "job_cards", label: "Job cards", icon: ClipboardList, path: (a) => `/${a}/job-cards` },
  { key: "invoices", label: "Invoices", icon: FileText, path: (a) => `/${a}/invoices` },
  { key: "vendors", label: "Workshops", icon: Building2, path: (a) => (a === "admin" ? "/admin/vendors" : null) },
];

/** Global search across customers, vehicles, bookings, invoices, job cards and workshops (tenant-scoped by the API). */
export function SearchPage() {
  const { user } = useAuth();
  const area = user?.role === "CUSTOMER" ? "customer" : user?.role === "SUPER_ADMIN" ? "admin" : "agency";
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  useEffect(() => {
    const t = setTimeout(() => draft !== q && setParams(draft ? { q: draft } : {}, { replace: true }), 300);
    return () => clearTimeout(t);
  }, [draft, q, setParams]);
  const results = useQuery({ queryKey: ["search", q], queryFn: () => reportsApi.search(q), enabled: q.trim().length >= 2 });
  const total = results.data ? Object.values(results.data).reduce((s, list) => s + (list?.length ?? 0), 0) : 0;

  return (
    <>
      <PageHeader title="Search" description="Names, phone numbers, e-mails, registration / VIN, booking, invoice and job card numbers." />
      <label className="relative mb-6 block">
        <span className="sr-only">Search</span>
        <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
        <input autoFocus type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Try MH12, BK-2026, a phone number…"
          className="block w-full rounded-2xl border-0 bg-white py-4 pl-12 pr-4 text-base shadow-[var(--shadow-soft)] ring-1 ring-slate-200 focus:shadow-[0_0_0_4px_rgb(101_96_244/0.12)] focus:outline-none focus:ring-2 focus:ring-brand-500" />
      </label>
      {q.trim().length < 2 ? <EmptyState title="Type at least 2 characters" /> : results.isLoading ? <Skeleton rows={5} /> : total === 0 ? (
        <EmptyState title={`No results for "${q}"`} />
      ) : (
        <div className="stagger grid gap-4 md:grid-cols-2">
          {GROUPS.filter((g) => results.data?.[g.key]?.length).map((g) => (
            <Card key={g.key} title={<span className="flex items-center gap-2"><g.icon className="h-4 w-4 text-brand-600" /> {g.label}</span>}>
              <ul className="divide-y divide-slate-100">
                {results.data![g.key]!.map((hit) => {
                  const base = g.path(area);
                  const inner = (
                    <div className="flex items-center gap-3 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-slate-900">{hit.title}</p>
                        <p className="truncate text-xs text-slate-500">{hit.subtitle}</p>
                      </div>
                      {hit.status && <StatusBadge status={hit.status} label={titleCase(hit.status)} />}
                    </div>
                  );
                  return <li key={hit.id}>{base ? <Link to={`${base}/${hit.id}`} className="block rounded-xl px-1 hover:bg-slate-50">{inner}</Link> : <div className="px-1">{inner}</div>}</li>;
                })}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
