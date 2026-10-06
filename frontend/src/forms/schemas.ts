import { z } from "zod";

const phone = z
  .string()
  .trim()
  .regex(/^\+?[0-9]{7,15}$/, "Enter 7–15 digits, optionally starting with +");
const optionalPhone = z.union([phone, z.literal("")]).optional();

export const passwordRule = z
  .string()
  .min(8, "At least 8 characters")
  .regex(/[A-Za-z]/, "Include a letter")
  .regex(/[0-9]/, "Include a number");

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid e-mail"),
  password: z.string().min(1, "Password is required"),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    full_name: z.string().trim().min(2, "Enter your full name").max(150),
    email: z.string().trim().email("Enter a valid e-mail"),
    phone: optionalPhone,
    password: passwordRule,
    confirm_password: z.string(),
  })
  .refine((v) => v.password === v.confirm_password, { path: ["confirm_password"], message: "Passwords do not match" });
export type RegisterValues = z.infer<typeof registerSchema>;

export const registerAgencySchema = z.object({
  name: z.string().trim().min(2, "Enter the agency name").max(200),
  email: z.string().trim().email("Enter a valid e-mail"),
  phone,
  city: z.string().trim().min(2, "Enter the city"),
  state: z.string().trim().optional(),
  pincode: z.string().trim().max(10).optional(),
  gst_number: z
    .union([z.string().trim().toUpperCase().regex(/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, "Invalid GSTIN"), z.literal("")])
    .optional(),
  address: z.string().trim().optional(),
  admin_full_name: z.string().trim().min(2, "Enter your full name"),
  admin_email: z.string().trim().email("Enter a valid e-mail"),
  admin_phone: optionalPhone,
  admin_password: passwordRule,
});
export type RegisterAgencyValues = z.infer<typeof registerAgencySchema>;

export const emailSchema = z.object({ email: z.string().trim().email("Enter a valid e-mail") });
export type EmailValues = z.infer<typeof emailSchema>;

export const resetPasswordSchema = z
  .object({ new_password: passwordRule, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, { path: ["confirm_password"], message: "Passwords do not match" });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

export const changePasswordSchema = z
  .object({ current_password: z.string().min(1, "Required"), new_password: passwordRule, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, { path: ["confirm_password"], message: "Passwords do not match" });
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

export const profileSchema = z.object({
  full_name: z.string().trim().min(2, "Enter your full name").max(150),
  phone: optionalPhone,
});
export type ProfileValues = z.infer<typeof profileSchema>;

export const organizationProfileSchema = z.object({
  name: z.string().trim().min(2).max(200),
  legal_name: z.string().trim().max(255).optional(),
  email: z.string().trim().email("Enter a valid e-mail"),
  phone,
  website: z.union([z.string().trim().url("Enter a full URL, e.g. https://…"), z.literal("")]).optional(),
  description: z.string().trim().optional(),
  address: z.string().trim().optional(),
  city: z.string().trim().min(2),
  state: z.string().trim().optional(),
  pincode: z.string().trim().max(10).optional(),
  gst_number: z
    .union([z.string().trim().toUpperCase().regex(/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, "Invalid GSTIN"), z.literal("")])
    .optional(),
  registration_number: z.string().trim().max(64).optional(),
});
export type OrganizationProfileValues = z.infer<typeof organizationProfileSchema>;
