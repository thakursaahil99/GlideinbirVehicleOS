import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";

import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { loginSchema } from "@/forms/schemas";
import { useAuth } from "@/hooks/useAuth";
import { homePathFor } from "@/utils/format";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFormError(null);
    try {
      const user = await login(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== "/login" ? from : homePathFor(user.role), { replace: true });
    } catch (err) {
      setFormError(applyApiErrors(err, setError, ["email", "password"]));
    }
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900 sm:text-3xl">
        Welcome back <span className="inline-block origin-[70%_70%] animate-[wave_1.6s_ease-in-out_2]">👋</span>
      </h2>
      <p className="mt-1 text-sm text-slate-500">Sign in to manage your vehicles, bookings or workshop.</p>

      <form onSubmit={onSubmit} className="stagger mt-8 space-y-4" noValidate>
        {formError && <Alert tone="danger">{formError}</Alert>}
        <Input label="E-mail" type="email" autoComplete="email" error={errors.email?.message} {...register("email")} />
        <Input label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm font-medium text-brand-600 hover:text-brand-700">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>
      </form>

      <div className="mt-6 space-y-2 text-center text-sm text-slate-600">
        <p>
          New customer?{" "}
          <Link to="/register" className="font-medium text-brand-600 hover:text-brand-700">
            Create an account
          </Link>
        </p>
        <p>
          Own a workshop?{" "}
          <Link to="/register-agency" className="font-medium text-brand-600 hover:text-brand-700">
            Register your agency
          </Link>
        </p>
      </div>

      {import.meta.env.DEV && (
        <div className="mt-8 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-3 text-xs text-slate-600">
          <p className="font-medium text-slate-700">Demo accounts (after <code>seed_demo_data</code>) — password <code>Demo@12345</code></p>
          <ul className="mt-1 space-y-0.5">
            <li>superadmin@demo.local</li>
            <li>admin@speedy-auto-care.demo.local</li>
            <li>staff@speedy-auto-care.demo.local</li>
            <li>customer01@demo.local</li>
          </ul>
        </div>
      )}
    </div>
  );
}
