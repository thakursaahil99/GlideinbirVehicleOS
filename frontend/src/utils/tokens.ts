/**
 * JWT storage. The access token is short-lived (15 min); the refresh token is
 * rotated on every refresh and blacklisted on logout by the backend.
 * See docs/SECURITY.md for the trade-off of browser storage vs httpOnly cookies.
 */
const ACCESS_KEY = "vsc.access";
const REFRESH_KEY = "vsc.refresh";

let accessToken: string | null = sessionStorage.getItem(ACCESS_KEY);

export const tokens = {
  getAccess: () => accessToken,
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set(access: string, refresh: string) {
    accessToken = access;
    sessionStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    accessToken = null;
    sessionStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  hasSession: () => Boolean(accessToken || localStorage.getItem(REFRESH_KEY)),
};
