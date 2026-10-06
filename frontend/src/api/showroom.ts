import { apiDelete, apiGetPage, apiPatch, apiPost, cleanParams } from "./client";

type Params = Record<string, unknown>;

export interface VehicleModel {
  id: string;
  vehicle_type: string;
  vehicle_type_display: string;
  brand: string;
  name: string;
  variant: string;
  launch_year: number | null;
  fuel_type: string;
  engine_cc: number | null;
  colours: string;
  ex_showroom_price: string | null;
  stock_quantity: number;
  minimum_stock: number;
  is_low_stock: boolean;
  is_active: boolean;
  notes: string;
}

export interface VehicleSale {
  id: string;
  vehicle_model: string;
  vehicle_model_name: string;
  customer: string | null;
  buyer_name: string;
  buyer_phone: string;
  buyer_email: string;
  buyer_address: string;
  colour: string;
  chassis_number: string;
  engine_number: string;
  registration_number: string;
  sale_price: string;
  payment_mode: string;
  invoice_number: string;
  sold_on: string;
  sold_by_name: string | null;
  notes: string;
}

export const showroomApi = {
  models: (params: Params = {}) => apiGetPage<VehicleModel>("/showroom/models/", cleanParams(params)),
  createModel: (input: Record<string, unknown>) => apiPost<VehicleModel>("/showroom/models/", input),
  updateModel: (id: string, input: Record<string, unknown>) => apiPatch<VehicleModel>(`/showroom/models/${id}/`, input),
  adjustStock: (id: string, quantity: number, note = "") => apiPost<VehicleModel>(`/showroom/models/${id}/stock/`, { quantity, note }),
  sales: (params: Params = {}) => apiGetPage<VehicleSale>("/showroom/sales/", cleanParams(params)),
  createSale: (input: Record<string, unknown>) => apiPost<VehicleSale>("/showroom/sales/", input),
  updateSale: (id: string, input: Record<string, unknown>) => apiPatch<VehicleSale>(`/showroom/sales/${id}/`, input),
  cancelSale: (id: string) => apiDelete(`/showroom/sales/${id}/`),
};
