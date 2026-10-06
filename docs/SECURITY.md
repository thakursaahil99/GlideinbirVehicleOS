# Security

> Multi-Vendor Vehicle Service CRM — **built by Sahil Thakur**

## Tenant isolation
* Tenant resolved server-side from the user's single **active membership** (DB-enforced uniqueness).
* All tenant reads go through `Model.objects.for_user(user)`; cross-tenant ids return **404**.
* Writes stamp `organization` from the membership; any client-sent organization is ignored.
* Object-level checks (`IsSameOrganization`, `IsOwner`) as defence in depth.
* Mandatory tests: `backend/tests/test_tenant_isolation.py` (orgs, members, audit logs, querysets,
  deactivated membership, DB constraint).

## Authentication
| Control | Implementation |
|---|---|
| Password hashing | Argon2 (PBKDF2 fallback for legacy hashes) |
| Password policy | Django validators: min length 8, common-password, numeric-only, similarity |
| Tokens | JWT access 15 min / refresh 7 days, rotation + blacklist after rotation |
| Revocation | Logout blacklists; password change/reset and deactivation revoke all refresh tokens |
| Inactive users | Rejected at login, on every access token use and at refresh |
| Enumeration | Same 401 `INVALID_CREDENTIALS` for unknown / wrong / inactive; reset request always 200 |
| Reset & verify links | HMAC tokens, single-use, time-limited; generated inside the Celery worker so no secret crosses Redis |
| Brute force | `auth` throttle scope (default 10/min per IP) on all credential endpoints |
| Role escalation | Registration ignores `role`; profile PATCH only accepts `full_name`, `phone`, `profile_photo` |

## Web
* CORS allow-list (`CORS_ALLOWED_ORIGINS`); credentials not allowed (JWT is sent in a header, not a cookie, so
  CSRF does not apply to the API; Django CSRF middleware still protects the admin site).
* Headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`,
  `Cross-Origin-Opener-Policy: same-origin`; production adds HSTS, SSL redirect, secure cookies.
* React escapes output by default; no `dangerouslySetInnerHTML`.
* ORM only — no raw SQL in request paths.

## Errors
* `api_exception_handler` returns a generic `INTERNAL_ERROR` for unhandled exceptions; the traceback is
  logged, never returned. `DEBUG=False` is forced in `prod.py`, and prod refuses to boot without a strong
  `DJANGO_SECRET_KEY`.

## Uploads
`ImageFileValidator` decodes the image with Pillow (does not trust extension or Content-Type), checks the
format against an allow-list (JPEG/PNG/WEBP), extension/content match, size, min/max dimensions and
decompression bombs. Filenames are sanitised and stored as `<prefix>/<yyyy>/<mm>/<uuid>.<ext>` — the client's
name never reaches the filesystem. S3 storage (prod) uses private ACL + signed URLs.

## Audit trail
* Logged: login, failed login, logout, password change/reset, e-mail verification, user create/update/
  activate/deactivate, agency register/update/approve/reject/suspend/reactivate/deactivate (later phases:
  bookings, payments, invoices, price and permission changes).
* Keys matching password/token/secret/api_key/authorization/… are replaced with `[REDACTED]`.
* Append-only: ORM `save`/`delete`/queryset `update`/`delete` raise, and a PostgreSQL trigger rejects
  `UPDATE`/`DELETE`.
* `X-Forwarded-For` is ignored unless `TRUST_X_FORWARDED_FOR=True` (set only behind a trusted proxy).

## Secrets
* All secrets come from environment variables; `.env` is git-ignored; `.env.example` holds placeholders only.
* Nothing secret is exposed via API, logs or audit data.

## Caching
Shared cache (Redis) is used for throttling and health checks only in Phase 1. Any future tenant data cache
**must** include the organization id in the key.

## Known trade-offs
* The SPA stores the refresh token in `localStorage` (access token in `sessionStorage` + memory). This is
  vulnerable to XSS token theft; mitigations are short access lifetime, rotation and blacklisting. Moving the
  refresh token to an `httpOnly; Secure; SameSite=Strict` cookie is planned for the Phase 12 security audit.
* Access tokens remain valid until expiry (≤15 min) after logout/deactivation; refresh is revoked immediately.
* The SPA's Content-Security-Policy is set by nginx (`docker/nginx/nginx.conf`); the API sets its own strict one.

## Money & stock integrity
* Every payment, refund, invoice change, price change and stock adjustment is audited with old/new values.
* Online payments accept an `idempotency_key`; a retried request returns the original payment instead of charging twice.
* Refunds are Agency-Admin-only, capped at the refundable balance, and go back through the provider that took the money.
* Invoice totals are computed with `Decimal` and ROUND_HALF_UP per line; money leaves the API as strings.
* Stock changes only through `InventoryService.move` under a row lock; a DB check constraint forbids negative stock and
  every movement gets a gap-free per-part ledger line number.

## Booking integrity
* Slots come only from `AvailabilityService`; `BookingService` re-validates under `SELECT … FOR UPDATE` and PostgreSQL
  rejects overlapping active bookings on one resource with an exclusion constraint (`btree_gist`).
* Concurrency tests race 5–6 threads for one slot: exactly the available capacity succeeds.

## Phase 12 audit (results)
| Area | Check | Result |
|---|---|---|
| AuthN | Sweep test: every non-public route returns 401 anonymously | ✅ all routes |
| Tenancy | Sweep test: agency B gets 403/404 on GET/PATCH/DELETE of every agency-A object type (11 types) | ✅ |
| Tenancy | Other customers get 404 on bookings, job cards, invoices, payments, vehicles | ✅ |
| Tenancy | Report/dashboard scope ignores `?organization=` for agency users | ✅ |
| Performance | Query-count budgets on bookings, customers, vehicles, invoices, job cards, calendar, dashboard | ✅ (no N+1) |
| Abuse | Scoped throttles: `auth` 10/min, `payments` 20/min (pay/record/refund), `search` 60/min | ✅ |
| Headers | API: `Content-Security-Policy: default-src 'none'`, `Cache-Control: no-store` for authenticated calls, `Permissions-Policy`, `X-Frame-Options: DENY`; nginx adds a strict CSP for the SPA | ✅ |
| Exports | CSV cells starting with `= + - @` are neutralised (CSV injection) | ✅ |
| Dependencies | `pip-audit` (prod requirements) and `npm audit --omit=dev` | ✅ clean after upgrading Pillow → 12.3 and DRF → 3.17.2 (both had CVEs) |
| Config | `manage.py check --deploy` | ✅ only W021 (HSTS preload is a deliberate opt-in via `SECURE_HSTS_PRELOAD`) |
| Schema | `spectacular --validate --fail-on-warn` | ✅ zero warnings |

Media in development is served by Django for convenience (UUID filenames, not guessable). In production use S3-compatible
private storage with signed URLs (`USE_S3_STORAGE=True`).

## Reporting
Report vulnerabilities privately to the project owner (Sahil Thakur).
