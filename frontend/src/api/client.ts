import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from "axios";

import type { ErrorEnvelope, Page, SuccessEnvelope } from "@/types/api";
import { tokens } from "@/utils/tokens";

export const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }

  /** Field errors from a VALIDATION_ERROR, flattened to first message per field. */
  fieldErrors(): Record<string, string> {
    if (!this.details) return {};
    const out: Record<string, string> = {};
    for (const [field, value] of Object.entries(this.details)) {
      out[field] = Array.isArray(value) ? String(value[0]) : String(value);
    }
    return out;
  }
}

// Arrays go as repeated keys (status=A&status=B), which django-filter expects.
export const api = axios.create({ baseURL: API_BASE_URL, timeout: 20_000, paramsSerializer: { indexes: null } });

api.interceptors.request.use((config) => {
  const access = tokens.getAccess();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

// Endpoints where a 401 means "bad credentials", not "expired access token".
const NO_REFRESH = ["/auth/login/", "/auth/refresh/", "/auth/register/", "/auth/register-agency/",
  "/auth/password-reset/", "/auth/verify-email/"];

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokens.getRefresh();
  if (!refresh) return null;
  try {
    const res = await axios.post<SuccessEnvelope<{ access: string; refresh?: string }>>(
      `${API_BASE_URL}/auth/refresh/`,
      { refresh },
    );
    const { access, refresh: rotated } = res.data.data;
    tokens.set(access, rotated ?? refresh);
    return access;
  } catch {
    tokens.clear();
    return null;
  }
}

function toApiError(error: AxiosError<ErrorEnvelope>): ApiError {
  const status = error.response?.status ?? 0;
  const payload = error.response?.data;
  if (payload && payload.success === false && payload.error) {
    return new ApiError(payload.error.message, payload.error.code, status, payload.error.details);
  }
  if (!error.response) {
    return new ApiError("Cannot reach the server. Check your connection.", "NETWORK_ERROR", 0);
  }
  return new ApiError("Something went wrong. Please try again.", "UNKNOWN_ERROR", status);
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ErrorEnvelope>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const url = original?.url ?? "";
    if (error.response?.status === 401 && original && !original._retried && !NO_REFRESH.some((p) => url.includes(p))) {
      original._retried = true;
      refreshInFlight ??= refreshAccessToken().finally(() => {
        refreshInFlight = null;
      });
      const access = await refreshInFlight;
      if (access) {
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      }
      window.dispatchEvent(new Event("auth:expired"));
    }
    throw toApiError(error);
  },
);

export async function apiGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get<SuccessEnvelope<T>>(url, { params });
  return res.data.data;
}

export async function apiGetPage<T>(url: string, params?: Record<string, unknown>): Promise<Page<T>> {
  const res = await api.get<SuccessEnvelope<T[]>>(url, { params });
  return { items: res.data.data, pagination: res.data.meta!.pagination };
}

export async function apiPost<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.post<SuccessEnvelope<T>>(url, body, config);
  return res.data.data;
}

export async function apiPatch<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.patch<SuccessEnvelope<T>>(url, body, config);
  return res.data.data;
}

export async function apiPut<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.put<SuccessEnvelope<T>>(url, body, config);
  return res.data.data;
}

export async function apiDelete(url: string): Promise<void> {
  await api.delete(url);
}

/** Remove empty values so they are not sent as filters. */
export function cleanParams(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v !== undefined && v !== null));
}
