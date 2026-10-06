import { useMutation } from "@tanstack/react-query";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/toast-context";
import { useAuth } from "@/hooks/useAuth";

export function VerifyEmailBanner() {
  const { user } = useAuth();
  const toast = useToast();
  const resend = useMutation({
    mutationFn: authApi.resendVerification,
    onSuccess: (r) => toast.show(r.message, "success"),
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Could not send e-mail.", "error"),
  });

  if (!user || user.email_verified) return null;
  return (
    <div className="mb-6 flex flex-col gap-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200 sm:flex-row sm:items-center sm:justify-between">
      <span>Please verify {user.email}. We sent you a link when you signed up.</span>
      <Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
        Resend link
      </Button>
    </div>
  );
}
