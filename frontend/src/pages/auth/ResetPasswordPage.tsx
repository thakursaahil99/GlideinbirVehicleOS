import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";

import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { resetPasswordSchema } from "@/forms/schemas";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(resetPasswordSchema), defaultValues: { new_password: "", confirm_password: "" } });

  const onSubmit = handleSubmit(async ({ new_password }) => {
    setFormError(null);
    try {
      await authApi.confirmPasswordReset(uid, token, new_password);
      setDone(true);
    } catch (err) {
      setFormError(applyApiErrors(err, setError, ["new_password"]));
    }
  });

  if (!uid || !token) return <Alert tone="danger">This reset link is incomplete. Request a new one.</Alert>;

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-900">Choose a new password</h2>
      {done ? (
        <div className="mt-8 space-y-4">
          <Alert tone="success">Your password has been reset. All other sessions were signed out.</Alert>
          <Link to="/login" className="block text-center text-sm font-medium text-brand-600">
            Sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
          {formError && <Alert tone="danger">{formError}</Alert>}
          <Input label="New password" type="password" autoComplete="new-password" error={errors.new_password?.message} {...register("new_password")} />
          <Input label="Confirm password" type="password" autoComplete="new-password" error={errors.confirm_password?.message} {...register("confirm_password")} />
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Reset password
          </Button>
        </form>
      )}
    </div>
  );
}
