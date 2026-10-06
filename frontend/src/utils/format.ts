import type { Role } from "@/types/api";

export const ROLE_LABELS: Record<Role, string> = {
  SUPER_ADMIN: "Super Admin",
  AGENCY_ADMIN: "Agency Admin",
  AGENCY_MANAGER: "Agency Manager",
  AGENCY_STAFF: "Agency Staff",
  CUSTOMER: "Customer",
};

export const AGENCY_ROLES: Role[] = ["AGENCY_ADMIN", "AGENCY_MANAGER", "AGENCY_STAFF"];

export function homePathFor(role: Role): string {
  if (role === "SUPER_ADMIN") return "/admin";
  if (AGENCY_ROLES.includes(role)) return "/agency";
  return "/customer";
}

const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});
const dateFmt = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" });

export const formatDateTime = (iso: string | null | undefined) => (iso ? dateTimeFmt.format(new Date(iso)) : "—");
export const formatDate = (iso: string | null | undefined) => (iso ? dateFmt.format(new Date(iso)) : "—");

export const titleCase = (value: string) =>
  value.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const VEHICLE_TYPE_LABELS: Record<string, string> = {
  CAR: "Car",
  BIKE: "Bike",
  SCOOTER: "Scooter",
  EV: "Electric vehicle",
  OTHER: "Other",
};

export const FUEL_LABELS: Record<string, string> = {
  PETROL: "Petrol",
  DIESEL: "Diesel",
  CNG: "CNG",
  LPG: "LPG",
  ELECTRIC: "Electric",
  HYBRID: "Hybrid",
  OTHER: "Other",
};

export const inr = (value: string | number | null | undefined) =>
  value === null || value === undefined || value === ""
    ? "—"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value));

/** True when an ISO date is in the past or within `days`. */
export const expiresSoon = (iso: string | null | undefined, days = 30) =>
  Boolean(iso) && new Date(iso!).getTime() - Date.now() < days * 86_400_000;

export const CATEGORY_LABELS: Record<string, string> = {
  MAINTENANCE: "Maintenance",
  REPAIR: "Repair",
  CLEANING: "Cleaning & detailing",
  TYRES_WHEELS: "Tyres & wheels",
  ELECTRICAL: "Electrical & battery",
  DIAGNOSTICS: "Diagnostics",
  ASSISTANCE: "Assistance",
  EMERGENCY: "Emergency",
};

export const formatDuration = (minutes: number) => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? (m ? `${h} h ${m} min` : `${h} h`) : `${m} min`;
};

export const BOOKING_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending", CONFIRMED: "Confirmed", ASSIGNED: "Assigned", VEHICLE_RECEIVED: "Vehicle received",
  IN_PROGRESS: "In progress", WAITING_FOR_APPROVAL: "Awaiting your approval", COMPLETED: "Completed",
  CANCELLED: "Cancelled", REJECTED: "Rejected", NO_SHOW: "No show",
};

export const timeOnly = (iso: string, tz = "Asia/Kolkata") =>
  new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: tz }).format(new Date(iso));

export const dayLabel = (isoDate: string) =>
  new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${isoDate}T00:00:00Z`));

/** Local YYYY-MM-DD (Asia/Kolkata) for today + offset days. */
export const isoDay = (offset = 0) => {
  const d = new Date(Date.now() + offset * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(d);
};
