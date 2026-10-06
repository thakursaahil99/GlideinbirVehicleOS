import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/toast-context";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { registerSchema } from "@/forms/schemas";
import { useAuth } from "@/hooks/useAuth";

export function RegisterPage() {
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
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: "", email: "", phone: "", password: "", confirm_password: "" },
  });

  const onSubmit = handleSubmit(async ({ confirm_password: _unused, ...values }) => {
    setFormError(null);
    try {
      startSession(await authApi.register(values));
      toast.show("Account created. Check your inbox to verify your e-mail.", "success");
      navigate("/customer", { replace: true });
    } catch (err) {
      setFormError(applyApiErrors(err, setError, ["full_name", "email", "phone", "password"]));
    }
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900">Create your account</h2>
      <p className="mt-1 text-sm text-slate-500">Book services and track your vehicles in one place.</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Input label="Full name" autoComplete="name" error={errors.full_name?.message} {...register("full_name")} />
        <Input label="E-mail" type="email" autoComplete="email" error={errors.email?.message} {...register("email")} />
        <Input label="Phone (optional)" type="tel" autoComplete="tel" placeholder="+919876543210" error={errors.phone?.message} {...register("phone")} />
        <Input label="Password" type="password" autoComplete="new-password" error={errors.password?.message} {...register("password")} />
        <Input label="Confirm password" type="password" autoComplete="new-password" error={errors.confirm_password?.message} {...register("confirm_password")} />
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Create account
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
