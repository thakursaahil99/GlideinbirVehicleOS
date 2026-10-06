import type { DatesSetArg, EventClickArg } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import listPlugin from "@fullcalendar/list";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { organizationsApi } from "@/api/resources";
import { bookingsApi } from "@/api/operations";
import { catalogApi } from "@/api/services";
import { Card, PageHeader } from "@/components/ui/Card";
import { Select } from "@/components/ui/FormField";
import { useAuth } from "@/hooks/useAuth";
import { BOOKING_STATUS_LABELS } from "@/utils/format";

import "./calendar.css";

const LEGEND: [string, string][] = [
  ["PENDING", "#f59e0b"], ["CONFIRMED", "#0ea5e9"], ["ASSIGNED", "#6366f1"], ["IN_PROGRESS", "#5243e6"],
  ["WAITING_FOR_APPROVAL", "#d97706"], ["COMPLETED", "#10b981"], ["CANCELLED", "#f43f5e"],
];

function useIsMobile() {
  const query = "(max-width: 640px)";
  const [mobile, setMobile] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMobile(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return mobile;
}

/** Day / week / month booking calendar. Super Admins can filter by agency, service and status. */
export function CalendarPage({ basePath }: { basePath: string }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "SUPER_ADMIN";
  const navigate = useNavigate();
  const mobile = useIsMobile();
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const [organization, setOrganization] = useState("");
  const [service, setService] = useState("");
  const [status, setStatus] = useState("");

  const agencies = useQuery({ queryKey: ["orgs", "all-active"], queryFn: () => organizationsApi.list({ status: "ACTIVE", page_size: 100 }), enabled: isAdmin });
  const services = useQuery({ queryKey: ["catalog", "all"], queryFn: () => catalogApi.list({ page_size: 100 }) });
  const events = useQuery({
    queryKey: ["bookings", "calendar", range, organization, service, status],
    queryFn: () => bookingsApi.calendar(range!.start, range!.end, { organization, service, status }),
    enabled: Boolean(range),
  });

  return (
    <>
      <PageHeader title="Calendar" description="Bookings by day, week or month, coloured by status." />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          {isAdmin && (
            <Select aria-label="Agency" value={organization} onChange={(e) => setOrganization(e.target.value)}>
              <option value="">All agencies</option>
              {agencies.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          )}
          <Select aria-label="Service" value={service} onChange={(e) => setService(e.target.value)}>
            <option value="">All services</option>
            {services.data?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {Object.entries(BOOKING_STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
          {LEGEND.map(([s, c]) => (
            <span key={s} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{BOOKING_STATUS_LABELS[s]}</span>
          ))}
        </div>
        <div className="crm-calendar -mx-2 sm:mx-0">
          <FullCalendar
            key={mobile ? "m" : "d"}
            plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
            initialView={mobile ? "listWeek" : "timeGridWeek"}
            headerToolbar={mobile
              ? { left: "prev,next", center: "title", right: "listWeek,dayGridMonth" }
              : { left: "prev,next today", center: "title", right: "timeGridDay,timeGridWeek,dayGridMonth,listWeek" }}
            buttonText={{ today: "Today", day: "Day", week: "Week", month: "Month", list: "List" }}
            timeZone="Asia/Kolkata"
            firstDay={1}
            slotMinTime="07:00:00"
            slotMaxTime="21:00:00"
            allDaySlot={false}
            nowIndicator
            height="auto"
            events={(events.data ?? []).map((e) => ({
              id: e.id, title: e.title, start: e.start, end: e.end, backgroundColor: e.color, borderColor: e.color,
              extendedProps: e.extended,
            }))}
            eventContent={(arg) => (
              <div className="overflow-hidden px-1 py-0.5 text-[11px] leading-tight">
                <b>{arg.timeText}</b> {arg.event.title}
                <div className="opacity-80">{String(arg.event.extendedProps.customer)}{arg.event.extendedProps.staff ? ` · ${arg.event.extendedProps.staff}` : ""}</div>
                {isAdmin && <div className="opacity-70">{String(arg.event.extendedProps.organization)}</div>}
              </div>
            )}
            datesSet={(arg: DatesSetArg) => setRange({ start: arg.start.toISOString(), end: arg.end.toISOString() })}
            eventClick={(arg: EventClickArg) => navigate(`${basePath}/${arg.event.id}`)}
          />
        </div>
      </Card>
    </>
  );
}
