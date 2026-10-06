import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { Spinner } from "@/components/ui/Card";
import { useAuth } from "@/hooks/useAuth";
import type { Role } from "@/types/api";
import { homePathFor } from "@/utils/format";

/** UI-level guard only — the backend enforces every permission independently. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <Spinner label="Restoring your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!roles.includes(user.role)) return <Navigate to="/forbidden" replace />;
  return <>{children}</>;
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();
  if (status === "loading") return <Spinner />;
  if (user) return <Navigate to={homePathFor(user.role)} replace />;
  return <>{children}</>;
}

export function HomeRedirect() {
  const { user, status } = useAuth();
  if (status === "loading") return <Spinner />;
  return <Navigate to={user ? homePathFor(user.role) : "/login"} replace />;
}
