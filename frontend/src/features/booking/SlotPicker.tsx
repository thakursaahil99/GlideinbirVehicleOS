import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { availabilityApi } from "@/api/operations";
import { Skeleton } from "@/components/ui/Card";
import type { Slot } from "@/types/operations";
import { cn, dayLabel, timeOnly } from "@/utils/format";

/** Day strip + live time slots for one vendor service. The backend decides availability. */
export function SlotPicker({ vendorService, selected, onSelect }: { vendorService: string; selected?: string; onSelect: (slot: Slot) => void }) {
  const [day, setDay] = useState<string | null>(null);
  const days = useQuery({ queryKey: ["availability", "days", vendorService], queryFn: () => availabilityApi.days(vendorService, 14) });
  const slots = useQuery({
    queryKey: ["availability", "slots", vendorService, day],
    queryFn: () => availabilityApi.slots(vendorService, day!),
    enabled: Boolean(day),
  });

  if (days.isLoading) return <Skeleton rows={2} />;
  return (
    <div className="space-y-4">
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {days.data?.days.map((d) => {
          const open = d.bookable && d.available_slots > 0;
          return (
            <button key={d.date} type="button" disabled={!open} onClick={() => setDay(d.date)}
              className={cn("shrink-0 rounded-xl px-3 py-2 text-center text-xs ring-1 transition",
                open ? "bg-white ring-slate-200 hover:ring-brand-400" : "bg-slate-50 text-slate-300 ring-slate-100",
                day === d.date && "ring-2 ring-brand-500")}>
              <span className="block font-medium">{dayLabel(d.date)}</span>
              <span className={open ? "text-emerald-600" : ""}>{d.total_slots === 0 ? "Closed" : `${d.available_slots} free`}</span>
            </button>
          );
        })}
      </div>
      {day && (slots.isLoading ? <Skeleton rows={1} /> : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {slots.data?.slots.length === 0 && <p className="col-span-full text-sm text-slate-500">No times left.</p>}
          {slots.data?.slots.map((s) => (
            <button key={s.start} type="button" disabled={!s.available} onClick={() => onSelect(s)}
              className={cn("rounded-xl py-2.5 text-sm font-medium ring-1",
                s.available ? "bg-white ring-slate-200 hover:ring-brand-400" : "bg-slate-50 text-slate-300 line-through ring-slate-100",
                selected === s.start && "bg-brand-600 text-white ring-brand-600")}>
              {timeOnly(s.start)}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
