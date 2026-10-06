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

  // On phones each row becomes a card: first column is the title, header-less columns
  // (row actions) form the footer, and the rest render as label/value pairs.
  const isAction = (col: Column<T>) => col.header === "" || col.key === "actions";
  const [titleCol, ...restCols] = columns;
  const fieldCols = restCols.filter((col) => !isAction(col) && !col.hideOnMobile);
  const actionCols = restCols.filter(isAction);

  return (
    <>
      <ul className={cn("stagger space-y-3 transition-opacity md:hidden", loading && "opacity-60")}>
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className="rounded-2xl bg-white p-4 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 transition-transform duration-150 active:scale-[0.99]"
          >
            {titleCol && <div className="min-w-0 text-sm font-medium text-slate-900">{titleCol.render(row)}</div>}
            {fieldCols.length > 0 && (
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 border-t border-slate-100 pt-3 text-sm">
                {fieldCols.map((col) => (
                  <div key={col.key} className="min-w-0">
                    <dt className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{col.header}</dt>
                    <dd className="mt-0.5 min-w-0 break-words text-slate-700">{col.render(row)}</dd>
                  </div>
                ))}
              </dl>
            )}
            {actionCols.length > 0 && (
              // Hidden when every action cell rendered nothing (e.g. no actions on your own account).
              <div className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-3 [&_button]:min-h-9 [&:not(:has(*>*))]:hidden">
                {actionCols.map((col) => (
                  <div key={col.key} className="flex flex-wrap justify-end gap-2 empty:hidden">
                    {col.render(row)}
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="-mx-4 hidden overflow-x-auto sm:-mx-5 md:block">
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
    </>
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
