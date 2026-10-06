import type { Customer, CustomerNote, Vehicle, VehicleDocument } from "@/types/api";

import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost, cleanParams } from "./client";

type Params = Record<string, unknown>;

export const customersApi = {
  list: (params: Params = {}) => apiGetPage<Customer>("/customers/", cleanParams(params)),
  get: (id: string) => apiGet<Customer>(`/customers/${id}/`),
  create: (input: Partial<Customer>) => apiPost<Customer>("/customers/", input),
  update: (id: string, input: Partial<Customer>) => apiPatch<Customer>(`/customers/${id}/`, input),
  notes: (id: string) => apiGetPage<CustomerNote>(`/customers/${id}/notes/`),
  addNote: (id: string, body: string) => apiPost<CustomerNote>(`/customers/${id}/notes/`, { body }),
  me: () => apiGet<Customer>("/customers/me/"),
  updateMe: (input: Partial<Customer>) => apiPatch<Customer>("/customers/me/", input),
};

export const vehiclesApi = {
  list: (params: Params = {}) => apiGetPage<Vehicle>("/vehicles/", cleanParams(params)),
  get: (id: string) => apiGet<Vehicle>(`/vehicles/${id}/`),
  create: (input: Partial<Vehicle>) => apiPost<Vehicle>("/vehicles/", input),
  update: (id: string, input: Partial<Vehicle>) => apiPatch<Vehicle>(`/vehicles/${id}/`, input),
  archive: (id: string) => apiDelete(`/vehicles/${id}/`),
  documents: (id: string) => apiGet<VehicleDocument[]>(`/vehicles/${id}/documents/`),
  uploadDocument: (id: string, form: FormData) => apiPost<VehicleDocument>(`/vehicles/${id}/documents/`, form),
  deleteDocument: (id: string, docId: string) => apiDelete(`/vehicles/${id}/documents/${docId}/`),
};
