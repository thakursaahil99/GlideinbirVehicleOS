export interface Pagination {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  next: string | null;
  previous: string | null;
}

export interface SuccessEnvelope<T> {
  success: true;
  data: T;
  meta?: { pagination: Pagination };
}

export interface ErrorEnvelope {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface Page<T> {
  items: T[];
  pagination: Pagination;
}

export type Role = "SUPER_ADMIN" | "AGENCY_ADMIN" | "AGENCY_MANAGER" | "AGENCY_STAFF" | "CUSTOMER";

export type OrganizationStatus = "PENDING" | "ACTIVE" | "INACTIVE" | "SUSPENDED" | "REJECTED";
export type VerificationStatus = "UNVERIFIED" | "PENDING" | "VERIFIED" | "REJECTED";

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  status: OrganizationStatus;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  role: Role;
  profile_photo: string | null;
  is_active: boolean;
  email_verified: boolean;
  date_joined: string;
  last_login: string | null;
  organization: OrganizationSummary | null;
  permissions: string[];
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface AuthResponse {
  user: User;
  tokens: TokenPair;
}

export interface Organization {
  id: string;
  name: string;
  legal_name: string;
  slug: string;
  logo: string | null;
  registration_number: string;
  gst_number: string;
  phone: string;
  email: string;
  website: string;
  description: string;
  address: string;
  city: string;
  state: string;
  country: string;
  pincode: string;
  latitude: string | null;
  longitude: string | null;
  status: OrganizationStatus;
  verification_status: VerificationStatus;
  status_reason: string;
  status_changed_at: string | null;
  created_at: string;
  updated_at: string;
  member_count?: number;
}

export interface Membership {
  id: string;
  user: Pick<User, "id" | "email" | "full_name" | "phone" | "role" | "is_active" | "last_login">;
  permissions: string[];
  is_active: boolean;
  created_at: string;
}

export interface AuditLog {
  id: string;
  action: string;
  user: string | null;
  user_email: string | null;
  organization: string | null;
  organization_name: string | null;
  model_name: string;
  object_id: string;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string;
  created_at: string;
}

export type StatusAction = "approve" | "reject" | "suspend" | "reactivate" | "deactivate";

// ---------------------------------------------------------------- Phase 2: agency operations
export interface StaffMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  phone: string;
  role: Role;
  profile_photo: string | null;
  permissions: string[];
  is_active: boolean;
  user_is_active: boolean;
  last_login: string | null;
  created_at: string;
}

export interface PermissionCode {
  code: string;
  label: string;
}

export interface WorkingInterval {
  id?: string;
  weekday: number;
  weekday_display?: string;
  opens_at: string;
  closes_at: string;
}

export type HolidayKind = "HOLIDAY" | "EMERGENCY_CLOSURE";

export interface Holiday {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  kind: HolidayKind;
  notes: string;
  created_at: string;
}

export interface SpecialDay {
  id: string;
  date: string;
  opens_at: string;
  closes_at: string;
  note: string;
}

export type ResourceType = "BAY" | "TECHNICIAN" | "EQUIPMENT" | "OTHER";

export interface ServiceResource {
  id: string;
  name: string;
  resource_type: ResourceType;
  staff: string | null;
  staff_name: string | null;
  description: string;
  active: boolean;
  created_at: string;
}

export interface AgencySettings {
  slot_interval_minutes: number | null;
  buffer_minutes: number;
  booking_lead_time_minutes: number;
  max_advance_days: number;
  cancellation_cutoff_hours: number;
  auto_confirm_bookings: boolean;
  additional_work_requires_approval: boolean;
  require_online_payment: boolean;
  updated_at: string;
}

export interface VendorPublic {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  description: string;
  phone: string;
  email: string;
  website: string;
  address: string;
  city: string;
  state: string;
  country: string;
  pincode: string;
  latitude: string | null;
  longitude: string | null;
  timezone: string;
  rating: number | null;
}

// ---------------------------------------------------------------- Phase 3: customers & vehicles
export type VehicleType = "CAR" | "BIKE" | "SCOOTER" | "EV" | "OTHER";
export type FuelType = "PETROL" | "DIESEL" | "CNG" | "LPG" | "ELECTRIC" | "HYBRID" | "OTHER";

export interface VehicleSummary {
  id: string;
  vehicle_type: VehicleType;
  brand: string;
  model: string;
  registration_number: string;
  is_active: boolean;
}

export interface Customer {
  id: string;
  full_name: string;
  phone: string;
  email: string;
  address: string;
  city: string;
  state: string;
  country: string;
  pincode: string;
  notes: string;
  is_walk_in: boolean;
  has_account: boolean;
  vehicle_count?: number;
  created_at: string;
  updated_at: string;
  vehicles?: VehicleSummary[];
  can_edit?: boolean;
}

export interface CustomerNote {
  id: string;
  body: string;
  author: string | null;
  author_name: string | null;
  created_at: string;
}

export interface Vehicle extends VehicleSummary {
  customer: string;
  customer_name: string;
  variant: string;
  vin: string;
  chassis_number: string;
  engine_number: string;
  fuel_type: FuelType;
  manufacturing_year: number | null;
  color: string;
  odometer: number | null;
  insurance_expiry: string | null;
  registration_expiry: string | null;
  pollution_expiry: string | null;
  notes: string;
  can_edit: boolean;
  created_at: string;
  updated_at: string;
}

export interface VehicleDocument {
  id: string;
  kind: "RC" | "INSURANCE" | "PUC" | "PHOTO" | "OTHER";
  title: string;
  file: string;
  uploaded_by: string | null;
  created_at: string;
}

// ---------------------------------------------------------------- Phase 4: services & pricing
export type ServiceCategory = "MAINTENANCE" | "REPAIR" | "CLEANING" | "TYRES_WHEELS" | "ELECTRICAL" | "DIAGNOSTICS" | "ASSISTANCE" | "EMERGENCY";

export interface CatalogService {
  id: string;
  name: string;
  slug: string;
  category: ServiceCategory;
  description?: string;
  supported_vehicle_types: VehicleType[];
  default_duration: number;
  base_price: string;
  tax: string;
  active?: boolean;
}

export interface VendorServiceOffering {
  id: string;
  service: string;
  service_detail: CatalogService;
  custom_price: string | null;
  custom_duration: number | null;
  price: string;
  duration: number;
  tax_rate: string;
  capacity: number;
  required_resource_type: ResourceType | "";
  active: boolean;
  pickup_available: boolean;
  drop_available: boolean;
  online_booking_enabled: boolean;
  description: string;
}

export interface PublicOffering {
  id: string;
  organization_id: string;
  organization_name: string;
  service: CatalogService;
  price: string;
  duration: number;
  tax_rate: string;
  pickup_available: boolean;
  drop_available: boolean;
  description: string;
}

export interface VendorOffer extends VendorPublic {
  offer_id: string;
  offer_price: string;
  offer_duration: number;
}
