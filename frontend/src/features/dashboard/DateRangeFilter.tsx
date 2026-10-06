import { Input } from "@/components/ui/FormField";
import { cn, isoDay } from "@/utils/format";

export interface Range {
  date_from: string;
  date_to: string;
}

const PRESETS: { label: string; days: number }[] = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
];

export const defaultRange = (): Range => ({ date_from: isoDay(-29), date_to: isoDay(0) });

/** One row: presets + custom dates (mobile: presets wrap above the date inputs). */
export function DateRangeFilter({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
      <div className="inline-flex rounded-xl bg-slate-200/60 p-1">
        {PRESETS.map((p) => {
          const active = value.date_from === isoDay(-(p.days - 1)) && value.date_to === isoDay(0);
          return (
            <button key={p.label} type="button" onClick={() => onChange({ date_from: isoDay(-(p.days - 1)), date_to: isoDay(0) })}
              className={cn("rounded-lg px-3 py-1.5 text-xs font-medium", active ? "bg-white text-brand-700 shadow" : "text-slate-500")}>
              {p.label}
            </button>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Input aria-label="From" type="date" value={value.date_from} onChange={(e) => onChange({ ...value, date_from: e.target.value })} />
        <Input aria-label="To" type="date" value={value.date_to} onChange={(e) => onChange({ ...value, date_to: e.target.value })} />
      </div>
    </div>
  );
}
