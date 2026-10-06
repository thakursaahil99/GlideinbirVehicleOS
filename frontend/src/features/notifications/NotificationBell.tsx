import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { Link } from "react-router";

import { notificationsApi } from "@/api/operations";
import { useAuth } from "@/hooks/useAuth";

/** Header bell with live unread count (polls every 60 s). */
export function NotificationBell() {
  const { user } = useAuth();
  const area = user?.role === "CUSTOMER" ? "customer" : user?.role === "SUPER_ADMIN" ? "admin" : "agency";
  const unread = useQuery({ queryKey: ["notifications", "unread"], queryFn: notificationsApi.unreadCount, refetchInterval: 60_000, enabled: Boolean(user) });
  const count = unread.data?.unread ?? 0;
  return (
    <Link to={`/${area}/notifications`} aria-label={`Notifications${count ? ` (${count} unread)` : ""}`}
      className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl text-slate-600 transition hover:bg-slate-100">
      <Bell className="h-5 w-5" />
      {count > 0 && (
        <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-gradient-to-br from-rose-500 to-rose-600 px-1 text-[10px] font-semibold text-white ring-2 ring-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
