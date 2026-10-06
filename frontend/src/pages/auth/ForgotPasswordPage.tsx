import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { emailSchema } from "@/forms/schemas";

export function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(emailSchema), defaultValues: { email: "" } });

  const onSubmit = handleSubmit(async ({ email }) => {
    setError(null);
    try {
      setSent((await authApi.requestPasswordReset(email)).message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900">Reset your password</h2>
      <p className="mt-1 text-sm text-slate-500">We'll e-mail you a link to choose a new password.</p>
      {sent ? (
        <div className="mt-8 space-y-4">
          <Alert tone="success">{sent}</Alert>
          <p className="text-xs text-slate-500">In development, e-mails are printed to the backend / Celery logs.</p>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
          {error && <Alert tone="danger">{error}</Alert>}
          <Input label="E-mail" type="email" autoComplete="email" error={errors.email?.message} {...register("email")} />
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Send reset link
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm">
        <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
