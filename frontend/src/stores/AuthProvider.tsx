import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { authApi } from "@/api/auth";
import type { AuthResponse, User } from "@/types/api";
import { tokens } from "@/utils/tokens";

import { AuthContext, type AuthStatus } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>(tokens.hasSession() ? "loading" : "anonymous");

  const endSession = useCallback(() => {
    tokens.clear();
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }, [queryClient]);

  // Restore the session on first load.
  useEffect(() => {
    if (!tokens.hasSession()) return;
    authApi
      .me()
      .then((me) => {
        setUser(me);
        setStatus("authenticated");
      })
      .catch(endSession);
  }, [endSession]);

  // The API client fires this when the refresh token is no longer valid.
  useEffect(() => {
    window.addEventListener("auth:expired", endSession);
    return () => window.removeEventListener("auth:expired", endSession);
  }, [endSession]);

  const startSession = useCallback((response: AuthResponse) => {
    tokens.set(response.tokens.access, response.tokens.refresh);
    setUser(response.user);
    setStatus("authenticated");
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await authApi.login(email, password);
      startSession(response);
      return response.user;
    },
    [startSession],
  );

  const logout = useCallback(async () => {
    const refresh = tokens.getRefresh();
    try {
      if (refresh) await authApi.logout(refresh);
    } catch {
      // Token may already be expired; the local session is cleared regardless.
    }
    endSession();
  }, [endSession]);

  const refreshUser = useCallback(async () => {
    setUser(await authApi.me());
  }, []);

  const value = useMemo(
    () => ({ user, status, login, startSession, logout, refreshUser }),
    [user, status, login, startSession, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
