import type { AuthResponse, Organization, User } from "@/types/api";

import { apiGet, apiPatch, apiPost } from "./client";

export interface RegisterCustomerInput {
  full_name: string;
  email: string;
  phone?: string;
  password: string;
}

export interface RegisterAgencyInput {
  name: string;
  phone: string;
  email: string;
  city: string;
  state?: string;
  gst_number?: string;
  address?: string;
  pincode?: string;
  admin_full_name: string;
  admin_email: string;
  admin_phone?: string;
  admin_password: string;
}

export const authApi = {
  login: (email: string, password: string) => apiPost<AuthResponse>("/auth/login/", { email, password }),
  register: (input: RegisterCustomerInput) => apiPost<AuthResponse>("/auth/register/", input),
  registerAgency: (input: RegisterAgencyInput) =>
    apiPost<AuthResponse & { organization: Organization }>("/auth/register-agency/", input),
  logout: (refresh: string) => apiPost<{ message: string }>("/auth/logout/", { refresh }),
  me: () => apiGet<User>("/auth/me/"),
  updateMe: (input: Partial<Pick<User, "full_name" | "phone">>) => apiPatch<User>("/auth/me/", input),
  changePassword: (current_password: string, new_password: string) =>
    apiPost<{ message: string }>("/auth/change-password/", { current_password, new_password }),
  requestPasswordReset: (email: string) => apiPost<{ message: string }>("/auth/password-reset/", { email }),
  confirmPasswordReset: (uid: string, token: string, new_password: string) =>
    apiPost<{ message: string }>("/auth/password-reset/confirm/", { uid, token, new_password }),
  verifyEmail: (uid: string, token: string) => apiPost<{ message: string }>("/auth/verify-email/", { uid, token }),
  resendVerification: () => apiPost<{ message: string }>("/auth/resend-verification/"),
};
