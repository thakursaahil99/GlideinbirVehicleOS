import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/toast-context";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { registerAgencySchema } from "@/forms/schemas";
import { useAuth } from "@/hooks/useAuth";

const FIELDS = [
  "name", "email", "phone", "city", "state", "pincode", "gst_number", "address",
  "admin_full_name", "admin_email", "admin_phone", "admin_password",
] as const;

export function RegisterAgencyPage() {
  const { startSession } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(registerAgencySchema),
    defaultValues: Object.fromEntries(FIELDS.map((f) => [f, ""])) as Record<(typeof FIELDS)[number], string>,
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      startSession(await authApi.registerAgency(values));
      toast.show("Agency registered. A Super Admin will review it shortly.", "success");
      navigate("/agency", { replace: true });
    } catch (err) {
      setFormError(applyApiErrors(err, setError, FIELDS));
    }
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900">Register your agency</h2>
      <p className="mt-1 text-sm text-slate-500">Your agency goes live after a Super Admin approves it.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-6" noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        <fieldset className="space-y-4">
          <legend className="text-sm font-semibold text-slate-900">Agency details</legend>
          <Input label="Agency name" error={errors.name?.message} {...register("name")} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Business e-mail" type="email" error={errors.email?.message} {...register("email")} />
            <Input label="Business phone" type="tel" placeholder="+912240000000" error={errors.phone?.message} {...register("phone")} />
            <Input label="City" error={errors.city?.message} {...register("city")} />
            <Input label="State" error={errors.state?.message} {...register("state")} />
            <Input label="PIN code" error={errors.pincode?.message} {...register("pincode")} />
            <Input label="GSTIN (optional)" error={errors.gst_number?.message} {...register("gst_number")} />
          </div>
          <Textarea label="Address" error={errors.address?.message} {...register("address")} />
        </fieldset>
        <fieldset className="space-y-4">
          <legend className="text-sm font-semibold text-slate-900">Your admin account</legend>
          <Input label="Full name" autoComplete="name" error={errors.admin_full_name?.message} {...register("admin_full_name")} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="E-mail" type="email" autoComplete="email" error={errors.admin_email?.message} {...register("admin_email")} />
            <Input label="Phone (optional)" type="tel" error={errors.admin_phone?.message} {...register("admin_phone")} />
          </div>
          <Input label="Password" type="password" autoComplete="new-password" error={errors.admin_password?.message} {...register("admin_password")} />
        </fieldset>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Submit for approval
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        Already registered?{" "}
        <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Sign in
        </Link>
      </p>
    </div>
  );
}
