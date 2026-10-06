import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/Button";
import { Card, PageHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/toast-context";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { changePasswordSchema, profileSchema } from "@/forms/schemas";
import { useAuth } from "@/hooks/useAuth";
import { ROLE_LABELS } from "@/utils/format";

import { VerifyEmailBanner } from "./VerifyEmailBanner";

function ProfileForm() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm({ resolver: zodResolver(profileSchema), defaultValues: { full_name: user?.full_name ?? "", phone: user?.phone ?? "" } });

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await authApi.updateMe({ full_name: values.full_name, phone: values.phone ?? "" });
      await refreshUser();
      reset({ full_name: updated.full_name, phone: updated.phone });
      toast.show("Profile updated.", "success");
    } catch (err) {
      const message = applyApiErrors(err, setError, ["full_name", "phone"]);
      if (message) toast.show(message, "error");
    }
  });

  return (
    <Card title="Personal details">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Input label="E-mail" value={user?.email ?? ""} disabled hint="Contact support to change your e-mail." readOnly />
        <Input label="Role" value={user ? ROLE_LABELS[user.role] : ""} disabled readOnly />
        <Input label="Full name" error={errors.full_name?.message} {...register("full_name")} />
        <Input label="Phone" type="tel" error={errors.phone?.message} {...register("phone")} />
        <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
          Save
        </Button>
      </form>
    </Card>
  );
}

function ChangePasswordForm() {
  const toast = useToast();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(changePasswordSchema), defaultValues: { current_password: "", new_password: "", confirm_password: "" } });

  const onSubmit = handleSubmit(async ({ current_password, new_password }) => {
    try {
      const res = await authApi.changePassword(current_password, new_password);
      reset();
      toast.show(res.message, "success");
    } catch (err) {
      const message = applyApiErrors(err, setError, ["current_password", "new_password"]);
      if (message) setError("current_password", { type: "server", message });
    }
  });

  return (
    <Card title="Change password">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Input label="Current password" type="password" autoComplete="current-password" error={errors.current_password?.message} {...register("current_password")} />
        <Input label="New password" type="password" autoComplete="new-password" error={errors.new_password?.message} {...register("new_password")} />
        <Input label="Confirm new password" type="password" autoComplete="new-password" error={errors.confirm_password?.message} {...register("confirm_password")} />
        <Button type="submit" loading={isSubmitting}>
          Update password
        </Button>
      </form>
    </Card>
  );
}

export function ProfilePage() {
  return (
    <>
      <PageHeader title="My profile" description="Manage your personal details and password." />
      <VerifyEmailBanner />
      <div className="grid gap-6 lg:grid-cols-2">
        <ProfileForm />
        <ChangePasswordForm />
      </div>
    </>
  );
}
