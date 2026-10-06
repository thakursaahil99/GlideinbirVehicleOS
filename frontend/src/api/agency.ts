import type {
  AgencySettings, Holiday, PermissionCode, ServiceResource, SpecialDay, StaffMember, VendorPublic, WorkingInterval,
} from "@/types/api";

import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost, apiPut, cleanParams } from "./client";

type Params = Record<string, unknown>;

export interface StaffInput {
  email?: string;
  full_name?: string;
  phone?: string;
  role?: string;
  permissions?: string[];
  /** New members only: set the first password now (blank = e-mail an invite link). */
  password?: string;
}

export const staffApi = {
  list: (params: Params = {}) => apiGetPage<StaffMember>("/agency/staff/", cleanParams(params)),
  create: (input: StaffInput) => apiPost<StaffMember>("/agency/staff/", input),
  update: (id: string, input: StaffInput) => apiPatch<StaffMember>(`/agency/staff/${id}/`, input),
  activate: (id: string) => apiPost<StaffMember>(`/agency/staff/${id}/activate/`),
  deactivate: (id: string) => apiPost<StaffMember>(`/agency/staff/${id}/deactivate/`),
  permissionCodes: () => apiGet<PermissionCode[]>("/agency/staff/permission-codes/"),
};

export const scheduleApi = {
  week: () => apiGet<WorkingInterval[]>("/agency/working-hours/"),
  replaceWeek: (intervals: WorkingInterval[]) => apiPut<WorkingInterval[]>("/agency/working-hours/week/", { intervals }),
  holidays: (params: Params = {}) => apiGetPage<Holiday>("/agency/holidays/", cleanParams(params)),
  createHoliday: (input: Omit<Holiday, "id" | "created_at">) => apiPost<Holiday>("/agency/holidays/", input),
  deleteHoliday: (id: string) => apiDelete(`/agency/holidays/${id}/`),
  specialDays: (params: Params = {}) => apiGetPage<SpecialDay>("/agency/special-days/", cleanParams(params)),
  setSpecialDay: (date: string, intervals: { opens_at: string; closes_at: string; note?: string }[]) =>
    apiPut<SpecialDay[]>("/agency/special-days/set-day/", { date, intervals }),
};

export const resourcesApi = {
  list: (params: Params = {}) => apiGetPage<ServiceResource>("/agency/resources/", cleanParams(params)),
  create: (input: Partial<ServiceResource>) => apiPost<ServiceResource>("/agency/resources/", input),
  update: (id: string, input: Partial<ServiceResource>) => apiPatch<ServiceResource>(`/agency/resources/${id}/`, input),
  remove: (id: string) => apiDelete(`/agency/resources/${id}/`),
};

export const agencySettingsApi = {
  get: () => apiGet<AgencySettings>("/agency/settings/"),
  update: (input: Partial<AgencySettings>) => apiPatch<AgencySettings>("/agency/settings/", input),
};

export const vendorsApi = {
  list: (params: Params = {}) => apiGetPage<VendorPublic>("/vendors/", cleanParams(params)),
  get: (id: string) => apiGet<VendorPublic>(`/vendors/${id}/`),
  hours: (id: string) =>
    apiGet<{ weekly: WorkingInterval[]; upcoming_closures: Pick<Holiday, "name" | "start_date" | "end_date">[] }>(
      `/vendors/${id}/hours/`,
    ),
};
