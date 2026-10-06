import {
  BarChart3, Bell, Bike, Building2, CalendarDays, CalendarPlus, Car, ClipboardList, Contact, CreditCard, FileClock, FileText,
  Gauge, Package, Search, Settings, Ticket, UserCircle, Users, Wrench, type LucideIcon,
} from "lucide-react";

import type { Role } from "@/types/api";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  roles?: Role[];
  /** Staff permission code required (admins hold all codes). */
  permission?: string;
}

// On phones the first four items form the bottom tab bar — keep the daily screens first.
export const NAVIGATION: Record<"admin" | "agency" | "customer", NavItem[]> = {
  admin: [
    { to: "/admin", label: "Dashboard", icon: Gauge, end: true },
    { to: "/admin/vendors", label: "Agencies", icon: Building2 },
    { to: "/admin/bookings", label: "Bookings", icon: Ticket },
    { to: "/admin/reports", label: "Reports", icon: BarChart3 },
    { to: "/admin/calendar", label: "Calendar", icon: CalendarDays },
    { to: "/admin/services", label: "Service catalog", icon: Wrench },
    { to: "/admin/customers", label: "Customers", icon: Contact },
    { to: "/admin/vehicles", label: "Vehicles", icon: Car },
    { to: "/admin/inventory", label: "Spare parts", icon: Package },
    { to: "/admin/invoices", label: "Invoices", icon: FileText },
    { to: "/admin/payments", label: "Payments", icon: CreditCard },
    { to: "/admin/users", label: "Users", icon: Users },
    { to: "/admin/audit-logs", label: "Audit logs", icon: FileClock },
    { to: "/admin/search", label: "Search", icon: Search },
    { to: "/admin/notifications", label: "Notifications", icon: Bell },
    { to: "/admin/profile", label: "My profile", icon: UserCircle },
  ],
  agency: [
    { to: "/agency", label: "Dashboard", icon: Gauge, end: true },
    { to: "/agency/bookings", label: "Bookings", icon: Ticket, permission: "BOOKING_VIEW" },
    { to: "/agency/calendar", label: "Calendar", icon: CalendarDays, permission: "BOOKING_VIEW" },
    { to: "/agency/job-cards", label: "Job cards", icon: ClipboardList, permission: "JOB_CARD_VIEW" },
    { to: "/agency/customers", label: "Customers", icon: Contact, permission: "CUSTOMER_VIEW" },
    { to: "/agency/vehicles", label: "Vehicles", icon: Car, permission: "VEHICLE_VIEW" },
    { to: "/agency/inventory", label: "Spare parts", icon: Package },
    { to: "/agency/showroom", label: "Showroom", icon: Bike },
    { to: "/agency/invoices", label: "Invoices", icon: FileText, permission: "INVOICE_VIEW" },
    { to: "/agency/payments", label: "Payments", icon: CreditCard, permission: "PAYMENT_VIEW" },
    { to: "/agency/reports", label: "Reports", icon: BarChart3, permission: "REPORT_VIEW" },
    { to: "/agency/services", label: "Services & pricing", icon: Wrench },
    { to: "/agency/staff", label: "Staff", icon: Users, roles: ["AGENCY_ADMIN", "AGENCY_MANAGER"] },
    { to: "/agency/settings", label: "Agency settings", icon: Settings },
    { to: "/agency/audit-logs", label: "Audit logs", icon: FileClock, roles: ["AGENCY_ADMIN"] },
    { to: "/agency/search", label: "Search", icon: Search },
    { to: "/agency/notifications", label: "Notifications", icon: Bell },
    { to: "/agency/profile", label: "My profile", icon: UserCircle },
  ],
  customer: [
    { to: "/customer", label: "Home", icon: Gauge, end: true },
    { to: "/customer/book", label: "Book", icon: CalendarPlus },
    { to: "/customer/bookings", label: "Bookings", icon: Ticket },
    { to: "/customer/vehicles", label: "My vehicles", icon: Car },
    { to: "/customer/invoices", label: "Invoices", icon: FileText },
    { to: "/customer/notifications", label: "Notifications", icon: Bell },
    { to: "/customer/profile", label: "My profile", icon: UserCircle },
  ],
};
