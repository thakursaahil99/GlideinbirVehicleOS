import type { CatalogService, PublicOffering, VendorOffer, VendorServiceOffering } from "@/types/api";

import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost, cleanParams } from "./client";

type Params = Record<string, unknown>;

export const catalogApi = {
  list: (params: Params = {}) => apiGetPage<CatalogService>("/services/", cleanParams(params)),
  get: (id: string) => apiGet<CatalogService>(`/services/${id}/`),
  create: (input: Partial<CatalogService>) => apiPost<CatalogService>("/services/", input),
  update: (id: string, input: Partial<CatalogService>) => apiPatch<CatalogService>(`/services/${id}/`, input),
};

export const offeringsApi = {
  list: (params: Params = {}) => apiGetPage<VendorServiceOffering>("/vendor-services/", cleanParams(params)),
  create: (input: Partial<VendorServiceOffering>) => apiPost<VendorServiceOffering>("/vendor-services/", input),
  update: (id: string, input: Partial<VendorServiceOffering>) => apiPatch<VendorServiceOffering>(`/vendor-services/${id}/`, input),
  remove: (id: string) => apiDelete(`/vendor-services/${id}/`),
};

export const directoryApi = {
  /** Agencies offering a service, with their price, for side-by-side comparison. */
  compare: (params: { service: string; vehicle_type?: string; city?: string; ordering?: string }) =>
    apiGetPage<VendorOffer>("/vendors/", cleanParams({ ...params, page_size: 50 })),
  services: (vendorId: string, vehicleType?: string) =>
    apiGetPage<PublicOffering>(`/vendors/${vendorId}/services/`, cleanParams({ vehicle_type: vehicleType, page_size: 100 })),
};
