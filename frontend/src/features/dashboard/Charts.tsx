/**
 * Dashboard charts (Recharts). Single-series by design: one brand hue
 * (#5243e6 — validated ≥3:1 on the light surface), thin marks, recessive grid,
 * one y-axis, hover tooltips on every mark, and a "Table" toggle for an
 * accessible data view.
 */
import { useId, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { cn } from "@/utils/format";

const MARK = "#5243e6";
const GRID = "#e2e8f0";
const INK_MUTED = "#64748b";

const money = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;
const shortDate = (iso: string) =>
  new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));

function TooltipBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/95 px-3 py-2 text-xs shadow-[var(--shadow-lift)] ring-1 ring-slate-200 backdrop-blur">
      <p className="text-slate-500">{label}</p>
      <p className="font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function ChartFrame({ title, total, rows, children }: { title: string; total?: string; rows: [string, string][]; children: React.ReactNode }) {
  const [table, setTable] = useState(false);
  return (
    <section className="animate-fade-up rounded-2xl bg-white p-4 shadow-[var(--shadow-soft)] ring-1 ring-slate-200/70 sm:p-5">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {total && <p className="font-display text-xl font-semibold text-slate-900">{total}</p>}
        </div>
        <button type="button" onClick={() => setTable(!table)} className="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">
          {table ? "Chart" : "Table"}
        </button>
      </header>
      {table ? (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {rows.map(([k, v]) => (
                <tr key={k}><td className="py-1.5 text-slate-600">{k}</td><td className="py-1.5 text-right font-medium text-slate-900">{v}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : children}
    </section>
  );
}

export function TrendChart({ title, data, kind }: { title: string; data: { date: string; value: number | string }[]; kind: "money" | "count" }) {
  const points = data.map((d) => ({ date: d.date, value: Number(d.value) }));
  const fmt = kind === "money" ? money : (v: number) => v.toLocaleString("en-IN");
  const total = points.reduce((s, p) => s + p.value, 0);
  // SVG ids must be unique and space-free or url(#…) silently falls back to black.
  const gradientId = `trend-fill-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <ChartFrame title={title} total={fmt(total)} rows={points.map((p) => [shortDate(p.date), fmt(p.value)])}>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          {kind === "money" ? (
            <AreaChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={MARK} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={MARK} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: INK_MUTED }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))} tick={{ fontSize: 11, fill: INK_MUTED }} tickLine={false} axisLine={false} width={36} />
              <Tooltip cursor={{ stroke: MARK, strokeDasharray: "3 3" }}
                content={({ active, payload, label }) => (active && payload?.length ? <TooltipBox label={shortDate(String(label))} value={fmt(Number(payload[0].value))} /> : null)} />
              <Area type="monotone" dataKey="value" stroke={MARK} strokeWidth={2} fill={`url(#${gradientId})`} activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2 }} />
            </AreaChart>
          ) : (
            <BarChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap={2}>
              <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: INK_MUTED }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: INK_MUTED }} tickLine={false} axisLine={false} width={28} />
              <Tooltip cursor={{ fill: "rgb(82 67 230 / 0.06)" }}
                content={({ active, payload, label }) => (active && payload?.length ? <TooltipBox label={shortDate(String(label))} value={`${payload[0].value} bookings`} /> : null)} />
              <Bar dataKey="value" fill={MARK} radius={[4, 4, 0, 0]} maxBarSize={18} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}

/** Ranked horizontal bars rendered in HTML: crisp on mobile, labels never collide. */
export function RankedBars({ title, rows, format = (v) => v.toLocaleString("en-IN"), empty = "No data yet" }: {
  title: string;
  rows: { label: string; value: number }[];
  format?: (v: number) => string;
  empty?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ChartFrame title={title} rows={rows.map((r) => [r.label, format(r.value)])}>
      {rows.length === 0 ? <p className="py-8 text-center text-sm text-slate-500">{empty}</p> : (
        <ul className="stagger space-y-2.5">
          {rows.map((r) => (
            <li key={r.label} className="group" title={`${r.label}: ${format(r.value)}`}>
              <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate text-slate-700">{r.label}</span>
                <span className="shrink-0 font-medium text-slate-900">{format(r.value)}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className={cn("h-full rounded-full bg-[#5243e6] transition-all duration-700 group-hover:brightness-110")} style={{ width: `${(r.value / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </ChartFrame>
  );
}

export const formatMoney = money;
