import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { scheduleApi } from "@/api/agency";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Card, Spinner } from "@/components/ui/Card";
import { useToast } from "@/components/ui/toast-context";
import type { WorkingInterval } from "@/types/api";

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const hhmm = (t: string) => t.slice(0, 5);

type Week = Record<number, { opens_at: string; closes_at: string }[]>;

const toWeek = (rows: WorkingInterval[]): Week => {
  const week: Week = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
  rows.forEach((r) => week[r.weekday].push({ opens_at: hhmm(r.opens_at), closes_at: hhmm(r.closes_at) }));
  return week;
};

const TEMPLATE: Week = Object.fromEntries(
  [0, 1, 2, 3, 4, 5, 6].map((d) => [d, d === 6 ? [] : [{ opens_at: "09:00", closes_at: "13:00" }, { opens_at: "14:00", closes_at: "19:00" }]]),
);

export function HoursTab({ canEdit }: { canEdit: boolean }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["agency", "hours"], queryFn: scheduleApi.week });
  const [week, setWeek] = useState<Week | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (query.data) {
      setWeek(toWeek(query.data));
      setDirty(false);
    }
  }, [query.data]);

  const save = useMutation({
    mutationFn: () =>
      scheduleApi.replaceWeek(Object.entries(week!).flatMap(([d, list]) => list.map((i) => ({ weekday: Number(d), ...i })))),
    onSuccess: (rows) => {
      queryClient.setQueryData(["agency", "hours"], rows);
      toast.show("Working hours saved.", "success");
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not save.", "error"),
  });

  if (query.isLoading || !week) return <Spinner />;

  const update = (day: number, list: Week[number]) => {
    setWeek({ ...week, [day]: list });
    setDirty(true);
  };

  return (
    <Card
      title="Weekly working hours"
      actions={
        canEdit && (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => { setWeek(TEMPLATE); setDirty(true); }}>Use 9–1 / 2–7 template</Button>
            <Button size="sm" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>Save hours</Button>
          </div>
        )
      }
    >
      <p className="mb-4 text-xs text-slate-500">
        Add several intervals per day for split shifts — the gaps between them are breaks. Days without intervals are closed.
        Slots are generated from these hours by the backend.
      </p>
      <div className="divide-y divide-slate-100">
        {WEEKDAYS.map((name, day) => (
          <div key={name} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start">
            <div className="w-32 shrink-0 pt-1.5 text-sm font-medium text-slate-800">{name}</div>
            <div className="flex-1 space-y-2">
              {week[day].length === 0 && <p className="pt-1.5 text-sm text-slate-400">Closed</p>}
              {week[day].map((iv, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input type="time" aria-label={`${name} opens`} value={iv.opens_at} disabled={!canEdit}
                    onChange={(e) => update(day, week[day].map((x, i) => (i === idx ? { ...x, opens_at: e.target.value } : x)))}
                    className="rounded-lg border-0 px-2 py-1.5 text-sm ring-1 ring-slate-300 focus:ring-2 focus:ring-brand-500" />
                  <span className="text-slate-400">–</span>
                  <input type="time" aria-label={`${name} closes`} value={iv.closes_at} disabled={!canEdit}
                    onChange={(e) => update(day, week[day].map((x, i) => (i === idx ? { ...x, closes_at: e.target.value } : x)))}
                    className="rounded-lg border-0 px-2 py-1.5 text-sm ring-1 ring-slate-300 focus:ring-2 focus:ring-brand-500" />
                  {canEdit && (
                    <button type="button" aria-label="Remove interval" className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                      onClick={() => update(day, week[day].filter((_, i) => i !== idx))}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
            {canEdit && (
              <Button size="sm" variant="ghost" onClick={() => {
                const last = week[day][week[day].length - 1];
                update(day, [...week[day], last ? { opens_at: last.closes_at, closes_at: "19:00" } : { opens_at: "09:00", closes_at: "18:00" }]);
              }}>
                <Plus className="h-4 w-4" /> Interval
              </Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
