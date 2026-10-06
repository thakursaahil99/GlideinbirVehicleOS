import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import type { Pagination as PaginationMeta } from "@/types/api";
import { cn } from "@/utils/format";

import { Button } from "./Button";
import { EmptyState, Skeleton } from "./Card";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
  /** Hide on small screens to keep tables readable on mobile. */
  hideOnMobile?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function DataTable<T>({ columns, rows, rowKey, loading, emptyTitle = "Nothing here yet", emptyDescription }: DataTableProps<T>) {
  if (loading && !rows) return <Skeleton />;
  if (!rows || rows.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;

  return (
    <div className="-mx-4 overflow-x-auto sm:-mx-5">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50/80">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 sm:px-5",
                  col.hideOnMobile && "hidden md:table-cell",
                  col.className,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={cn("stagger divide-y divide-slate-100 bg-white transition-opacity", loading && "opacity-60")}>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="transition-colors duration-150 hover:bg-brand-50/40">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn("px-4 py-3 align-middle text-slate-700 sm:px-5", col.hideOnMobile && "hidden md:table-cell", col.className)}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ meta, onPageChange }: { meta?: PaginationMeta; onPageChange: (page: number) => void }) {
  if (!meta || meta.total_pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between gap-2 text-sm text-slate-600">
      <span>
        Page {meta.page} of {meta.total_pages} · {meta.count} total
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={!meta.previous} onClick={() => onPageChange(meta.page - 1)} aria-label="Previous page">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button variant="secondary" size="sm" disabled={!meta.next} onClick={() => onPageChange(meta.page + 1)} aria-label="Next page">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
