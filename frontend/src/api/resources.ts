import type { AuditLog, Membership, Organization, StatusAction, User } from "@/types/api";

import { apiGet, apiGetPage, apiPatch, apiPost, cleanParams } from "./client";

type Params = Record<string, unknown>;

export interface UserCreateInput {
  email: string;
  full_name: string;
  phone?: string;
  role: string;
  /** Required for agency roles. */
  organization?: string | null;
  /** Blank = e-mail a link to set the password. */
  password?: string;
}

export interface AgencyCreateInput {
  name: string;
  email: string;
  phone: string;
  city: string;
  state?: string;
  address?: string;
  pincode?: string;
  gst_number?: string;
  admin_full_name: string;
  admin_email: string;
  admin_phone?: string;
  admin_password?: string;
}

export const organizationsApi = {
  list: (params: Params = {}) => apiGetPage<Organization>("/organizations/", cleanParams(params)),
  create: (input: AgencyCreateInput) => apiPost<Organization>("/organizations/", input),
  get: (id: string) => apiGet<Organization>(`/organizations/${id}/`),
  update: (id: string, input: Partial<Organization>) => apiPatch<Organization>(`/organizations/${id}/`, input),
  changeStatus: (id: string, action: StatusAction, reason = "") =>
    apiPost<Organization>(`/organizations/${id}/${action}/`, { reason }),
  members: (id: string, params: Params = {}) =>
    apiGetPage<Membership>(`/organizations/${id}/members/`, cleanParams(params)),
};

export const usersApi = {
  list: (params: Params = {}) => apiGetPage<User>("/users/", cleanParams(params)),
  create: (input: UserCreateInput) => apiPost<User>("/users/", input),
  update: (id: string, input: Record<string, string>) => apiPatch<User>(`/users/${id}/`, input),
  activate: (id: string) => apiPost<User>(`/users/${id}/activate/`),
  deactivate: (id: string) => apiPost<User>(`/users/${id}/deactivate/`),
};

export const auditLogsApi = {
  list: (params: Params = {}) => apiGetPage<AuditLog>("/audit-logs/", cleanParams(params)),
};
