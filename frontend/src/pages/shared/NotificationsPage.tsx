import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { Link } from "react-router";

import { notificationsApi } from "@/api/operations";
import { Button } from "@/components/ui/Button";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/Card";
import { useAuth } from "@/hooks/useAuth";
import type { AppNotification } from "@/types/operations";
import { cn, formatDateTime } from "@/utils/format";

export function notificationLink(n: AppNotification, area: string) {
  if (n.data.invoice_id) return `/${area}/invoices/${n.data.invoice_id}`;
  if (n.data.booking_id) return `/${area}/bookings/${n.data.booking_id}`;
  return null;
}

export function NotificationsPage() {
  const { user } = useAuth();
  const area = user?.role === "CUSTOMER" ? "customer" : user?.role === "SUPER_ADMIN" ? "admin" : "agency";
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: ["notifications", "inbox"],
    queryFn: ({ pageParam }) => notificationsApi.list({ page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.pagination.next ? last.pagination.page + 1 : undefined),
  });
  const markAll = useMutation({
    mutationFn: () => notificationsApi.markRead(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markOne = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead([id]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader title="Notifications" description="Booking updates, approvals, invoices and payments."
        actions={<Button variant="secondary" loading={markAll.isPending} onClick={() => markAll.mutate()}><CheckCheck className="h-4 w-4" /> Mark all read</Button>} />
      <Card>
        {query.isLoading ? <Skeleton rows={5} /> : items.length === 0 ? <EmptyState title="You're all caught up" /> : (
          <ul className="stagger divide-y divide-slate-100">
            {items.map((n) => {
              const link = notificationLink(n, area);
              const body = (
                <div className="flex gap-3 py-3">
                  <span className={cn("mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", n.is_read ? "bg-slate-100 text-slate-400" : "bg-gradient-to-br from-brand-500 to-accent-500 text-white")}>
                    <Bell className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={cn("text-sm", n.is_read ? "text-slate-600" : "font-semibold text-slate-900")}>{n.title}</p>
                    <p className="text-sm text-slate-600">{n.body}</p>
                    <p className="mt-0.5 text-xs text-slate-400">{formatDateTime(n.created_at)}</p>
                  </div>
                  {!n.is_read && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-brand-500" aria-label="Unread" />}
                </div>
              );
              return (
                <li key={n.id} onClick={() => !n.is_read && markOne.mutate(n.id)}>
                  {link ? <Link to={link} className="block rounded-xl px-2 hover:bg-slate-50">{body}</Link> : <div className="px-2">{body}</div>}
                </li>
              );
            })}
          </ul>
        )}
        {query.hasNextPage && (
          <div className="mt-4 flex justify-center"><Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>Load more</Button></div>
        )}
      </Card>
    </>
  );
}
