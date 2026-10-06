import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Alert, Spinner } from "@/components/ui/Card";
import { useAuth } from "@/hooks/useAuth";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const { user, refreshUser } = useAuth();
  const [state, setState] = useState<{ status: "pending" | "ok" | "error"; message?: string }>({ status: "pending" });
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode double-invokes effects; the token is single-use.
    started.current = true;
    const uid = params.get("uid");
    const token = params.get("token");
    if (!uid || !token) {
      setState({ status: "error", message: "This verification link is incomplete." });
      return;
    }
    authApi
      .verifyEmail(uid, token)
      .then(async () => {
        setState({ status: "ok" });
        if (user) await refreshUser();
      })
      .catch((err) => setState({ status: "error", message: err instanceof ApiError ? err.message : "Verification failed." }));
  }, [params, user, refreshUser]);

  return (
    <div>
      <h2 className="mb-6 text-2xl font-semibold text-slate-900">E-mail verification</h2>
      {state.status === "pending" && <Spinner label="Verifying…" />}
      {state.status === "ok" && <Alert tone="success">Your e-mail address is verified.</Alert>}
      {state.status === "error" && <Alert tone="danger">{state.message}</Alert>}
      <Link to="/" className="mt-6 block text-center text-sm font-medium text-brand-600">
        Continue
      </Link>
    </div>
  );
}
