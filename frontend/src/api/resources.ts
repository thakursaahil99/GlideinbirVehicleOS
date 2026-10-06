import type { AuditLog, Membership, Organization, StatusAction, User } from "@/types/api";

import { apiGet, apiGetPage, apiPatch, apiPost, cleanParams } from "./client";

type Params = Record<string, unknown>;

export const organizationsApi = {
  list: (params: Params = {}) => apiGetPage<Organization>("/organizations/", cleanParams(params)),
  get: (id: string) => apiGet<Organization>(`/organizations/${id}/`),
  update: (id: string, input: Partial<Organization>) => apiPatch<Organization>(`/organizations/${id}/`, input),
  changeStatus: (id: string, action: StatusAction, reason = "") =>
    apiPost<Organization>(`/organizations/${id}/${action}/`, { reason }),
  members: (id: string, params: Params = {}) =>
    apiGetPage<Membership>(`/organizations/${id}/members/`, cleanParams(params)),
};

export const usersApi = {
  list: (params: Params = {}) => apiGetPage<User>("/users/", cleanParams(params)),
  activate: (id: string) => apiPost<User>(`/users/${id}/activate/`),
  deactivate: (id: string) => apiPost<User>(`/users/${id}/deactivate/`),
};

export const auditLogsApi = {
  list: (params: Params = {}) => apiGetPage<AuditLog>("/audit-logs/", cleanParams(params)),
};
