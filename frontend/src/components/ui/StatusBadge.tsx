import { cn, titleCase } from "@/utils/format";

type Tone = "green" | "amber" | "slate" | "rose" | "blue" | "violet";

const tones: Record<Tone, { badge: string; dot: string }> = {
  green: { badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  amber: { badge: "bg-amber-50 text-amber-700 ring-amber-600/20", dot: "bg-amber-500" },
  slate: { badge: "bg-slate-100 text-slate-600 ring-slate-500/20", dot: "bg-slate-400" },
  rose: { badge: "bg-rose-50 text-rose-700 ring-rose-600/20", dot: "bg-rose-500" },
  blue: { badge: "bg-sky-50 text-sky-700 ring-sky-600/20", dot: "bg-sky-500" },
  violet: { badge: "bg-brand-50 text-brand-700 ring-brand-600/20", dot: "bg-brand-500" },
};

const statusTone: Record<string, Tone> = {
  ACTIVE: "green", VERIFIED: "green", APPROVED: "green", COMPLETED: "green", DELIVERED: "green", PAID: "green", SUCCESS: "green", SUCCEEDED: "green", READY: "green", IN_STOCK: "green",
  PENDING: "amber", AWAITING_APPROVAL: "amber", WAITING_APPROVAL: "amber", WAITING_FOR_APPROVAL: "amber", PARTIALLY_PAID: "amber", UNPAID: "amber", DUE: "amber", ON_HOLD: "amber", LOW_STOCK: "amber",
  INACTIVE: "slate", UNVERIFIED: "slate", DRAFT: "slate", CLOSED: "slate", EXPIRED: "slate",
  SUSPENDED: "rose", REJECTED: "rose", CANCELLED: "rose", FAILED: "rose", OVERDUE: "rose", NO_SHOW: "rose", OUT_OF_STOCK: "rose", VOID: "rose",
  CONFIRMED: "blue", SCHEDULED: "blue", CHECKED_IN: "blue", ASSIGNED: "blue", VEHICLE_RECEIVED: "blue", OPEN: "blue", ISSUED: "blue", REFUNDED: "blue",
  IN_PROGRESS: "violet", IN_SERVICE: "violet", QUALITY_CHECK: "violet", WORK_IN_PROGRESS: "violet", INSPECTION: "violet",
};

/** Statuses that represent work in motion get a pulsing dot. */
const live = new Set([
  "PENDING", "IN_PROGRESS", "IN_SERVICE", "CHECKED_IN", "AWAITING_APPROVAL", "QUALITY_CHECK",
  "WORK_IN_PROGRESS", "INSPECTION", "WAITING_APPROVAL", "WAITING_FOR_APPROVAL",
]);

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const t = tones[statusTone[status] ?? "violet"];
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", t.badge)}>
      <span className="relative flex h-1.5 w-1.5">
        {live.has(status) && <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", t.dot)} />}
        <span className={cn("relative h-1.5 w-1.5 rounded-full", t.dot)} />
      </span>
      {label ?? titleCase(status)}
    </span>
  );
}
