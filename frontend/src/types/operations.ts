// Phases 5–11: availability, bookings, workshop, finance, notifications, reports.

export type BookingStatus =
  | "PENDING" | "CONFIRMED" | "ASSIGNED" | "VEHICLE_RECEIVED" | "IN_PROGRESS" | "WAITING_FOR_APPROVAL"
  | "COMPLETED" | "CANCELLED" | "REJECTED" | "NO_SHOW";

export type BookingAction =
  | "confirm" | "reject" | "receive_vehicle" | "start" | "complete" | "no_show" | "cancel" | "reschedule" | "assign";

export interface Slot {
  start: string;
  end: string;
  available: boolean;
  remaining: number;
  reason: string;
}

export interface SlotsResponse {
  date: string;
  timezone: string;
  vendor_service: string;
  duration_minutes: number;
  slots: Slot[];
}

export interface DaysResponse {
  timezone: string;
  window: { first: string; last: string };
  days: { date: string; bookable: boolean; available_slots: number; total_slots: number }[];
}

export interface Booking {
  id: string;
  booking_number: string;
  status: BookingStatus;
  status_color: string;
  payment_status: "UNPAID" | "PARTIALLY_PAID" | "PAID" | "REFUNDED";
  source: "ONLINE" | "AGENCY";
  organization: { id: string; name: string; phone: string };
  customer: { id: string; full_name: string; phone: string };
  vehicle: { id: string; brand: string; model: string; registration_number: string; vehicle_type: string };
  service: { id: string; name: string; category: string };
  vendor_service: string;
  booking_date: string;
  start_datetime: string;
  end_datetime: string;
  duration_minutes: number;
  quoted_price: string;
  tax_rate: string;
  assigned_staff: { id: string; full_name: string } | null;
  assigned_resource: { id: string; name: string; resource_type: string } | null;
  customer_notes: string;
  internal_notes?: string;
  pickup_requested: boolean;
  drop_requested: boolean;
  pickup_address: string;
  confirmed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  allowed_actions: BookingAction[];
  job_card_id: string | null;
  invoice_id: string | null;
  created_at: string;
}

export interface BookingHistory {
  status: { id: string; from_status: string; to_status: string; changed_by_name: string | null; note: string; created_at: string }[];
  reschedules: { id: string; old_start: string; new_start: string; reason: string; rescheduled_by_name: string | null; created_at: string }[];
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  color: string;
  status: BookingStatus;
  extended: { booking_number: string; customer: string; vehicle: string; service: string; organization: string; staff: string | null; resource: string | null };
}

export type JobCardStatus = "OPEN" | "INSPECTION" | "WORK_IN_PROGRESS" | "WAITING_APPROVAL" | "COMPLETED" | "CLOSED";

export interface InspectionItem {
  id: string;
  area: string;
  stage: "BEFORE" | "AFTER";
  result: "OK" | "ATTENTION" | "REPLACE" | "NOT_CHECKED";
  notes: string;
}

export interface AdditionalWork {
  id: string;
  description: string;
  estimated_cost: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  customer_response: string;
  approved_at: string | null;
  rejected_at: string | null;
  auto_approved: boolean;
  created_at: string;
}

export interface JobCardPart {
  id: string;
  part: string;
  part_name: string;
  sku?: string;
  quantity: string;
  returned_quantity: string;
  net_quantity: string;
  unit_price: string;
  tax_rate: string;
}

export interface JobCard {
  id: string;
  job_card_number: string;
  status: JobCardStatus;
  booking: { id: string; booking_number: string; status: BookingStatus; service: string; start_datetime: string; assigned_staff: string | null };
  vehicle: { id: string; brand: string; model: string; registration_number: string; vehicle_type: string };
  customer: { id: string; full_name: string; phone: string };
  inspection_notes: string;
  vehicle_condition: string;
  odometer: number | null;
  fuel_level: string;
  existing_damage: string;
  customer_requests: string;
  technician_notes: string;
  inspection_items?: InspectionItem[];
  photos?: { id: string; stage: string; image: string; caption: string; created_at: string }[];
  additional_work?: AdditionalWork[];
  parts_used?: JobCardPart[];
  completed_at: string | null;
  closed_at: string | null;
  created_at: string;
}

export interface PartFitment {
  id?: string;
  vehicle_type: string;
  brand: string;
  model: string;
  year_from: number | null;
  year_to: number | null;
}

export interface Part {
  id: string;
  organization: string;
  organization_name: string;
  name: string;
  sku: string;
  brand: string;
  category: string | null;
  category_name: string | null;
  preferred_supplier: string | null;
  preferred_supplier_name: string | null;
  hsn_code: string;
  rack_location: string;
  description: string;
  universal: boolean;
  fitments: PartFitment[];
  stock_status: "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";
  purchase_price: string;
  selling_price: string;
  tax_rate: string;
  stock_quantity: string;
  minimum_stock: string;
  unit: string;
  active: boolean;
  is_low_stock: boolean;
}

export interface StockTransaction {
  id: string;
  part_name: string;
  transaction_type: string;
  quantity: string;
  unit_price: string;
  balance_after: string;
  supplier_name?: string | null;
  job_card_number: string | null;
  reference: string;
  note: string;
  created_by_name: string | null;
  created_at: string;
}

export interface PartCategory {
  id: string;
  name: string;
  description: string;
  parts_count: number;
}

export interface Supplier {
  id: string;
  name: string;
  contact_person: string;
  phone: string;
  email: string;
  gst_number: string;
  address: string;
  notes: string;
  active: boolean;
  parts_count: number;
  purchase_count: number;
  purchase_total: string;
  last_purchase_at: string | null;
}

export interface FitmentOption {
  vehicle_type: string;
  brand: string;
  model: string;
  parts: number;
}

export interface InventorySummary {
  parts: number;
  stock_value_cost: string;
  stock_value_retail: string;
  low_stock: number;
  out_of_stock: number;
  by_category: { category: string; parts: number; value: string }[];
  dead_stock_days: number;
  dead_stock: { id: string; name: string; sku: string; stock_quantity: string; unit: string; value: string; last_out_at: string | null }[];
}

export interface InvoiceItem {
  id: string;
  item_type: string;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax_rate: string;
  tax_amount: string;
  total: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  status: "DRAFT" | "ISSUED" | "VOID";
  organization: string;
  organization_name: string;
  customer: string;
  customer_name: string;
  booking: string | null;
  booking_number: string | null;
  subtotal: string;
  discount: string;
  tax: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  payment_status: string;
  invoice_date: string;
  notes: string;
  items?: InvoiceItem[];
  has_pdf: boolean;
  void_reason: string;
}

export interface Payment {
  id: string;
  invoice: string | null;
  invoice_number: string | null;
  booking: string | null;
  booking_number: string | null;
  customer_name: string;
  amount: string;
  refunded_amount: string;
  method: string;
  status: "PENDING" | "SUCCEEDED" | "FAILED" | "REFUNDED" | "PARTIALLY_REFUNDED";
  gateway: string;
  transaction_id: string;
  reference: string;
  failure_reason: string;
  paid_at: string | null;
  created_at: string;
}

export interface AppNotification {
  id: string;
  event: string;
  title: string;
  body: string;
  data: Record<string, string>;
  is_read: boolean;
  created_at: string;
}

export interface SeriesPoint {
  date: string;
  value: number | string;
}

export interface Dashboard {
  role: "SUPER_ADMIN" | "AGENCY" | "CUSTOMER";
  stats: Record<string, number | string>;
  charts?: {
    revenue: SeriesPoint[];
    bookings: SeriesPoint[];
    popular_services: { name: string; bookings: number }[];
    agency_performance?: { name: string; revenue: string; bookings: number }[];
    vehicle_types?: { type: string; count: number }[];
    cancellation?: { total: number; cancelled: number; rate: number };
    staff_utilization?: { staff: string; bookings: number; completed: number; hours: number; completion_rate: number }[];
  };
  today?: { id: string; booking_number: string; start: string; status: BookingStatus; customer: string; service: string; vehicle: string }[];
  upcoming_booking?: { id: string; booking_number: string; start: string; status: BookingStatus; agency: string; service: string; vehicle: string } | null;
  period?: { from: string; to: string };
}

export interface ReportResult {
  name: string;
  title: string;
  columns: string[];
  rows: Record<string, string | number | null>[];
  period: { from: string; to: string };
}

export interface TimelineEvent {
  at: string;
  type: string;
  title: string;
  detail: string;
  agency: string;
  ref: string;
}

export interface SearchHit {
  id: string;
  title: string;
  subtitle: string;
  status?: string;
}

export type SearchResults = Record<"customers" | "vehicles" | "bookings" | "invoices" | "job_cards" | "vendors", SearchHit[] | undefined>;
