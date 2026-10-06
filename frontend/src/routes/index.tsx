import { lazy, Suspense, type ComponentType, type ReactNode } from "react";
import { createBrowserRouter } from "react-router";

import { Skeleton } from "@/components/ui/Card";
import { CustomerInsights } from "@/features/customers/CustomerInsights";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";
import { AdminAgenciesPage } from "@/pages/admin/AdminAgenciesPage";
import { AdminServicesPage } from "@/pages/admin/AdminServicesPage";
import { AdminUsersPage } from "@/pages/admin/AdminUsersPage";
import { AuditLogsPage } from "@/pages/admin/AuditLogsPage";
import { AgencyServicesPage } from "@/pages/agency/AgencyServicesPage";
import { AgencySettingsPage } from "@/pages/agency/AgencySettingsPage";
import { AgencyStaffPage } from "@/pages/agency/AgencyStaffPage";
import { InventoryPage } from "@/pages/agency/InventoryPage";
import { ShowroomPage } from "@/pages/agency/ShowroomPage";
import { ForgotPasswordPage } from "@/pages/auth/ForgotPasswordPage";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterAgencyPage } from "@/pages/auth/RegisterAgencyPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";
import { VerifyEmailPage } from "@/pages/auth/VerifyEmailPage";
import { BookServicePage } from "@/pages/customer/BookServicePage";
import { CustomerVehiclesPage } from "@/pages/customer/CustomerVehiclesPage";
import { ForbiddenPage, NotFoundPage } from "@/pages/ErrorPages";
import { ProfilePage } from "@/pages/ProfilePage";
import { BookingDetailPage } from "@/pages/shared/BookingDetailPage";
import { BookingsPage } from "@/pages/shared/BookingsPage";
import { CustomerDetailPage } from "@/pages/shared/CustomerDetailPage";
import { CustomersListPage } from "@/pages/shared/CustomersListPage";
import { InvoiceDetailPage } from "@/pages/shared/InvoiceDetailPage";
import { InvoicesPage } from "@/pages/shared/InvoicesPage";
import { JobCardDetailPage } from "@/pages/shared/JobCardDetailPage";
import { JobCardsPage } from "@/pages/shared/JobCardsPage";
import { NotificationsPage } from "@/pages/shared/NotificationsPage";
import { PaymentsPage } from "@/pages/shared/PaymentsPage";
import { SearchPage } from "@/pages/shared/SearchPage";
import { VehiclesListPage } from "@/pages/shared/VehiclesListPage";

import { GuestOnly, HomeRedirect, RequireRole } from "./guards";

// Chart- and calendar-heavy pages load on demand to keep the first paint small on phones.
const named = <K extends string>(loader: () => Promise<Record<K, ComponentType<never>>>, key: K) =>
  lazy(async () => ({ default: (await loader())[key] as ComponentType }));
const AdminDashboard = named(() => import("@/pages/admin/AdminDashboard"), "AdminDashboard");
const AgencyDashboard = named(() => import("@/pages/agency/AgencyDashboard"), "AgencyDashboard");
const CustomerDashboard = named(() => import("@/pages/customer/CustomerDashboard"), "CustomerDashboard");
const ReportsPage = named(() => import("@/pages/shared/ReportsPage"), "ReportsPage");
const CalendarPage = lazy(async () => ({ default: (await import("@/pages/shared/CalendarPage")).CalendarPage }));

const later = (node: ReactNode) => <Suspense fallback={<Skeleton rows={6} />}>{node}</Suspense>;
const AGENCY = ["AGENCY_ADMIN", "AGENCY_MANAGER", "AGENCY_STAFF"] as const;

/** Pages every signed-in area shares, mounted under /admin, /agency and /customer. */
function sharedRoutes(area: "admin" | "agency" | "customer") {
  const base = `/${area}`;
  return [
    { path: "bookings", element: <BookingsPage basePath={`${base}/bookings`} /> },
    { path: "bookings/:id", element: <BookingDetailPage backTo={`${base}/bookings`} /> },
    { path: "job-cards", element: <JobCardsPage basePath={`${base}/job-cards`} /> },
    { path: "job-cards/:id", element: <JobCardDetailPage backTo={`${base}/job-cards`} /> },
    { path: "invoices", element: <InvoicesPage basePath={`${base}/invoices`} /> },
    { path: "invoices/:id", element: <InvoiceDetailPage backTo={`${base}/invoices`} /> },
    { path: "notifications", element: <NotificationsPage /> },
    { path: "search", element: <SearchPage /> },
    { path: "profile", element: <ProfilePage /> },
  ];
}

export const router = createBrowserRouter([
  { path: "/", element: <HomeRedirect /> },
  {
    element: <AuthLayout />,
    children: [
      { path: "/login", element: <GuestOnly><LoginPage /></GuestOnly> },
      { path: "/register", element: <GuestOnly><RegisterPage /></GuestOnly> },
      { path: "/register-agency", element: <GuestOnly><RegisterAgencyPage /></GuestOnly> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/verify-email", element: <VerifyEmailPage /> },
    ],
  },
  {
    path: "/admin",
    element: <RequireRole roles={["SUPER_ADMIN"]}><AppLayout area="admin" /></RequireRole>,
    children: [
      { index: true, element: later(<AdminDashboard />) },
      { path: "vendors", element: <AdminAgenciesPage /> },
      { path: "inventory", element: <InventoryPage /> },
      { path: "services", element: <AdminServicesPage /> },
      { path: "customers", element: <CustomersListPage basePath="/admin/customers" /> },
      { path: "customers/:id", element: <CustomerDetailPage backTo="/admin/customers"><CustomerInsights bookingsBase="/admin/bookings" /></CustomerDetailPage> },
      { path: "vehicles", element: <VehiclesListPage /> },
      { path: "calendar", element: later(<CalendarPage basePath="/admin/bookings" />) },
      { path: "payments", element: <PaymentsPage /> },
      { path: "reports", element: later(<ReportsPage />) },
      { path: "users", element: <AdminUsersPage /> },
      { path: "audit-logs", element: <AuditLogsPage /> },
      ...sharedRoutes("admin"),
    ],
  },
  {
    path: "/agency",
    element: <RequireRole roles={[...AGENCY]}><AppLayout area="agency" /></RequireRole>,
    children: [
      { index: true, element: later(<AgencyDashboard />) },
      { path: "calendar", element: later(<CalendarPage basePath="/agency/bookings" />) },
      { path: "customers", element: <CustomersListPage basePath="/agency/customers" /> },
      { path: "customers/:id", element: <CustomerDetailPage backTo="/agency/customers"><CustomerInsights bookingsBase="/agency/bookings" /></CustomerDetailPage> },
      { path: "vehicles", element: <VehiclesListPage /> },
      { path: "inventory", element: <InventoryPage /> },
      { path: "showroom", element: <ShowroomPage /> },
      { path: "payments", element: <PaymentsPage /> },
      { path: "reports", element: later(<ReportsPage />) },
      { path: "services", element: <AgencyServicesPage /> },
      { path: "staff", element: <RequireRole roles={["AGENCY_ADMIN", "AGENCY_MANAGER"]}><AgencyStaffPage /></RequireRole> },
      { path: "settings", element: <AgencySettingsPage /> },
      { path: "audit-logs", element: <RequireRole roles={["AGENCY_ADMIN"]}><AuditLogsPage /></RequireRole> },
      ...sharedRoutes("agency"),
    ],
  },
  {
    path: "/customer",
    element: <RequireRole roles={["CUSTOMER"]}><AppLayout area="customer" /></RequireRole>,
    children: [
      { index: true, element: later(<CustomerDashboard />) },
      { path: "book", element: <BookServicePage /> },
      { path: "vehicles", element: <CustomerVehiclesPage /> },
      ...sharedRoutes("customer"),
    ],
  },
  { path: "/forbidden", element: <ForbiddenPage /> },
  { path: "*", element: <NotFoundPage /> },
]);
