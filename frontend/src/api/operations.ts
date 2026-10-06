import type {
  AdditionalWork, AppNotification, Booking, BookingHistory, CalendarEvent, Dashboard, DaysResponse, Invoice, JobCard,
  JobCardPart, Part, Payment, ReportResult, SearchResults, SlotsResponse, StockTransaction, TimelineEvent,
} from "@/types/operations";

import { api, apiGet, apiGetPage, apiPatch, apiPost, apiPut, cleanParams } from "./client";

type Params = Record<string, unknown>;

export const availabilityApi = {
  slots: (vendorService: string, date: string) =>
    apiGet<SlotsResponse>("/availability/slots/", { vendor_service: vendorService, date }),
  days: (vendorService: string, days = 14, start?: string) =>
    apiGet<DaysResponse>("/availability/days/", cleanParams({ vendor_service: vendorService, days, start })),
};

export interface CreateBookingInput {
  vendor_service: string;
  vehicle: string;
  start_datetime: string;
  customer?: string;
  customer_notes?: string;
  pickup_requested?: boolean;
  drop_requested?: boolean;
  pickup_address?: string;
}

export const bookingsApi = {
  list: (params: Params = {}) => apiGetPage<Booking>("/bookings/", cleanParams(params)),
  get: (id: string) => apiGet<Booking>(`/bookings/${id}/`),
  create: (input: CreateBookingInput) => apiPost<Booking>("/bookings/", input),
  updateNotes: (id: string, input: { customer_notes?: string; internal_notes?: string }) => apiPatch<Booking>(`/bookings/${id}/`, input),
  transition: (id: string, action: "confirm" | "reject" | "receive-vehicle" | "start" | "complete" | "no-show", note = "") =>
    apiPost<Booking>(`/bookings/${id}/${action}/`, { note }),
  cancel: (id: string, reason: string) => apiPost<Booking>(`/bookings/${id}/cancel/`, { reason }),
  reschedule: (id: string, start_datetime: string, reason = "") => apiPost<Booking>(`/bookings/${id}/reschedule/`, { start_datetime, reason }),
  assign: (id: string, input: { staff?: string | null; resource?: string | null }) => apiPost<Booking>(`/bookings/${id}/assign/`, input),
  history: (id: string) => apiGet<BookingHistory>(`/bookings/${id}/history/`),
  calendar: (start: string, end: string, params: Params = {}) =>
    apiGet<CalendarEvent[]>("/bookings/calendar/", cleanParams({ start, end, ...params })),
};

export const jobCardsApi = {
  list: (params: Params = {}) => apiGetPage<JobCard>("/job-cards/", cleanParams(params)),
  get: (id: string) => apiGet<JobCard>(`/job-cards/${id}/`),
  update: (id: string, input: Partial<JobCard>) => apiPatch<JobCard>(`/job-cards/${id}/`, input),
  saveInspection: (id: string, items: { area: string; stage?: string; result: string; notes?: string }[]) =>
    apiPut<JobCard>(`/job-cards/${id}/inspection/`, { items }),
  uploadPhoto: (id: string, form: FormData) => apiPost(`/job-cards/${id}/photos/`, form),
  startWork: (id: string) => apiPost<JobCard>(`/job-cards/${id}/start-work/`),
  requestWork: (id: string, description: string, estimated_cost: string) =>
    apiPost<AdditionalWork>(`/job-cards/${id}/additional-work/`, { description, estimated_cost }),
  respondWork: (id: string, workId: string, approve: boolean, response = "") =>
    apiPost<AdditionalWork>(`/job-cards/${id}/additional-work/${workId}/respond/`, { approve, response }),
  cancelWork: (id: string, workId: string) => apiPost<AdditionalWork>(`/job-cards/${id}/additional-work/${workId}/cancel/`),
  usePart: (id: string, part: string, quantity: string) => apiPost<JobCardPart>(`/job-cards/${id}/parts/`, { part, quantity }),
  returnPart: (id: string, usageId: string, quantity: string) =>
    apiPost<JobCardPart>(`/job-cards/${id}/parts/${usageId}/return/`, { quantity }),
  complete: (id: string, technician_notes?: string) => apiPost<JobCard>(`/job-cards/${id}/complete/`, { technician_notes }),
  close: (id: string) => apiPost<JobCard>(`/job-cards/${id}/close/`),
};

export const inventoryApi = {
  list: (params: Params = {}) => apiGetPage<Part>("/inventory/parts/", cleanParams(params)),
  create: (input: Partial<Part>) => apiPost<Part>("/inventory/parts/", input),
  update: (id: string, input: Partial<Part>) => apiPatch<Part>(`/inventory/parts/${id}/`, input),
  move: (id: string, input: { transaction_type: string; quantity: string; unit_price?: string; reference?: string; note?: string }) =>
    apiPost<StockTransaction>(`/inventory/parts/${id}/move/`, input),
  transactions: (id: string) => apiGetPage<StockTransaction>(`/inventory/parts/${id}/transactions/`),
};

export const invoicesApi = {
  list: (params: Params = {}) => apiGetPage<Invoice>("/invoices/", cleanParams(params)),
  get: (id: string) => apiGet<Invoice>(`/invoices/${id}/`),
  update: (id: string, input: { discount?: string; notes?: string }) => apiPatch<Invoice>(`/invoices/${id}/`, input),
  void: (id: string, reason: string) => apiPost<Invoice>(`/invoices/${id}/void/`, { reason }),
  /** Downloads the PDF with the auth header and opens the browser's save dialog. */
  downloadPdf: async (id: string, filename: string) => {
    const res = await api.get(`/invoices/${id}/pdf/`, { responseType: "blob" });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
};

export const paymentsApi = {
  list: (params: Params = {}) => apiGetPage<Payment>("/payments/", cleanParams(params)),
  pay: (input: { invoice?: string; payment?: string; method: string; simulate?: "success" | "fail"; idempotency_key?: string }) =>
    apiPost<Payment>("/payments/pay/", input),
  record: (input: { invoice: string; amount: string; method: string; reference?: string }) => apiPost<Payment>("/payments/record/", input),
  refund: (id: string, amount: string | undefined, reason: string) => apiPost<Payment>(`/payments/${id}/refund/`, { amount, reason }),
};

export const notificationsApi = {
  list: (params: Params = {}) => apiGetPage<AppNotification>("/notifications/", cleanParams(params)),
  unreadCount: () => apiGet<{ unread: number }>("/notifications/unread-count/"),
  markRead: (ids?: string[]) => apiPost<{ updated: number }>("/notifications/mark-read/", ids ? { ids } : {}),
};

export const reportsApi = {
  dashboard: (params: Params = {}) => apiGet<Dashboard>("/reports/dashboard/", cleanParams(params)),
  catalog: () => apiGet<{ name: string; title: string }[]>("/reports/"),
  run: (name: string, params: Params = {}) => apiGet<ReportResult>(`/reports/${name}/`, cleanParams(params)),
  download: async (name: string, format: "csv" | "xlsx", params: Params = {}) => {
    const res = await api.get(`/reports/${name}/`, { params: cleanParams({ ...params, export: format }), responseType: "blob" });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.${format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
  search: (q: string) => apiGet<SearchResults>("/search/", { q }),
  timeline: (customerId: string | "me") =>
    apiGet<TimelineEvent[]>(customerId === "me" ? "/customers/me/timeline/" : `/customers/${customerId}/timeline/`),
  customerSummary: (customerId: string) =>
    apiGet<{ total_spending: string; pending_payments: string; bookings_count: number; completed_services: number; upcoming_bookings: Booking[]; booking_history: Booking[] }>(
      `/customers/${customerId}/summary/`,
    ),
};
