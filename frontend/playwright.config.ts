/**
 * End-to-end browser tests (built by Sahil Thakur).
 *
 * Every run starts from a fresh, seeded SQLite database (backend/e2e.sqlite3) with its own
 * API (:8030) and web app (:5199), so it never touches your dev data or running servers.
 *   npm run e2e            # headless, desktop + mobile
 *   npm run e2e -- --ui    # interactive
 */
import { existsSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const backendDir = resolve(import.meta.dirname, "../backend");
const python = existsSync(join(backendDir, ".venv/Scripts/python.exe"))
  ? join(backendDir, ".venv/Scripts/python.exe")
  : join(backendDir, ".venv/bin/python");
const API_PORT = 8030;
const WEB_PORT = 5199;

// Fresh database once per run. Playwright re-evaluates this file in every worker process,
// so the reset is guarded by an env flag the workers inherit (otherwise they'd delete the
// database the already-running test server is using).
if (!process.env.PW_REUSE && !process.env.E2E_DB_RESET_DONE) {
  for (const suffix of ["", "-wal", "-shm"]) rmSync(join(backendDir, `e2e.sqlite3${suffix}`), { force: true });
  process.env.E2E_DB_RESET_DONE = "1";
}

const backendEnv = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: "config.settings.dev",
  DATABASE_URL: "sqlite:///e2e.sqlite3",
  DJANGO_DEBUG: "True",
  THROTTLE_AUTH: "1000/min",
  THROTTLE_PAYMENTS: "1000/min",
  PYTHONIOENCODING: "utf-8",
};
delete (backendEnv as Record<string, string | undefined>).REDIS_URL;
delete (backendEnv as Record<string, string | undefined>).CACHE_URL;

const py = `"${python}"`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1, // one SQLite database, flows build on each other
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    timezoneId: "Asia/Kolkata",
    locale: "en-IN",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `${py} manage.py migrate --noinput -v0 && ${py} manage.py seed_demo_data && ${py} manage.py runserver 127.0.0.1:${API_PORT} --noreload`,
      cwd: backendDir,
      env: backendEnv as Record<string, string>,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health/`,
      timeout: 240_000,
      reuseExistingServer: Boolean(process.env.PW_REUSE),
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { ...process.env, VITE_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` } as Record<string, string>,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 120_000,
      reuseExistingServer: Boolean(process.env.PW_REUSE),
    },
  ],
});
