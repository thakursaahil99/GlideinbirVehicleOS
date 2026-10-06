# API

> Glideinbir — Vehicle Operating System — **built by Sahil Thakur**

* Base URL: `/api/v1/` · Swagger UI: **`/api/v1/docs/`** · schema: `/api/v1/schema/` (both off by default in production)
* Auth: `Authorization: Bearer <access token>` (15-minute access, 7-day rotating refresh)
* Everything not listed as *public* returns `401 NOT_AUTHENTICATED` without a token (enforced by a sweep test over every route).

## Response envelope

```jsonc
{ "success": true, "data": { ... } }                                   // success
{ "success": true, "data": [ ... ], "meta": { "pagination": {          // paginated list
    "count": 42, "page": 1, "page_size": 20, "total_pages": 3, "next": "…", "previous": null } } }
{ "success": false, "error": { "code": "BOOKING_SLOT_UNAVAILABLE",     // error
    "message": "Selected time slot is no longer available.", "details": { ... } } }
```

Pagination `?page=&page_size=` (≤100) · search `?search=` · ordering `?ordering=-created_at` · multi-value filters repeat
the key (`?status=PENDING&status=CONFIRMED`). Money is always a decimal **string** (`"3499.00"`), never a float.
Datetimes are ISO 8601 with offset; agency-local times use the agency's `timezone` (default `Asia/Kolkata`).

### Error codes (selection)

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Field errors in `details` |
| 400 | `BUSINESS_RULE_VIOLATION`, `REASON_REQUIRED`, `VEHICLE_TYPE_NOT_SUPPORTED`, `SERVICE_NOT_BOOKABLE`, `PICKUP_ADDRESS_REQUIRED`, `CUTOFF_PASSED`, `INSUFFICIENT_STOCK`, `NOTE_REQUIRED`, `INVALID_AMOUNT`, `INVOICE_HAS_PAYMENTS`, `APPROVAL_PENDING`, `JOB_CARD_LOCKED`, `DUPLICATE_VEHICLE`, `EMAIL_TAKEN`, `CANNOT_MANAGE_ADMIN`, `CANNOT_MODIFY_SELF`, `OVERLAPPING_INTERVALS`, `NO_RESOURCES_OF_TYPE`, `SERVICE_ALREADY_OFFERED` | Domain rule broken |
| 401 | `NOT_AUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_INVALID`, `USER_INACTIVE` | Auth |
| 403 | `PERMISSION_DENIED`, `CUSTOMER_SELF_MANAGED`, `VEHICLE_SELF_MANAGED` | Role / permission code missing |
| 404 | `NOT_FOUND` (+ `VEHICLE_NOT_FOUND`, `CUSTOMER_NOT_FOUND`, …) | Missing **or another tenant's** |
| 409 | `BOOKING_SLOT_UNAVAILABLE`, `VEHICLE_ALREADY_BOOKED`, `STAFF_CONFLICT`, `RESOURCE_CONFLICT`, `INVALID_STATE_TRANSITION`, `RESOURCE_IN_USE` | Conflict |
| 429 | `RATE_LIMITED` | Throttled (`Retry-After` set) |
| 500 | `INTERNAL_ERROR` | Logged server-side; no details leave the server |

## Endpoints

### System & auth
| Method | Path | Access |
|---|---|---|
| GET | `health/` | public |
| POST | `auth/register/` · `auth/register-agency/` · `auth/login/` · `auth/refresh/` · `auth/password-reset/` · `auth/password-reset/confirm/` · `auth/verify-email/` | public, `auth` throttle |
| POST | `auth/logout/` · `auth/change-password/` · `auth/resend-verification/` | signed in |
| GET/PATCH | `auth/me/` | signed in |

### Platform (Super Admin)
| Method | Path | Notes |
|---|---|---|
| GET | `users/` · `users/{id}/`; POST `users/{id}/activate|deactivate/` | |
| GET/PATCH | `organizations/` · `organizations/{id}/` | agency users: own only |
| POST | `organizations/{id}/approve|reject|suspend|reactivate|deactivate/` | reasons required for reject/suspend |
| GET | `organizations/{id}/members/` | Super Admin / own Admin & Manager |
| GET | `audit-logs/` · `audit-logs/{id}/` | Super Admin: all · Agency Admin: own |
| GET/POST/PATCH | `services/` · `services/{id}/` | catalog; writes Super Admin only |

### Agency operations (`agency/`)
| Method | Path | Access |
|---|---|---|
| GET/POST, PATCH | `agency/staff/`, `agency/staff/{id}/`; POST `…/activate|deactivate/`; GET `agency/staff/permission-codes/` | read: Admin/Manager · write: Admin |
| GET; PUT `agency/working-hours/week/` | weekly hours (multiple intervals/day) | read: members · write: Admin |
| CRUD | `agency/holidays/` | " |
| GET; PUT `agency/special-days/set-day/` | per-date overrides | " |
| CRUD | `agency/resources/` | bays / technicians / equipment |
| GET/PATCH | `agency/settings/` | buffer, lead time, window, cutoff, auto-confirm, approvals, prepayment |
| CRUD | `vendor-services/` | own offerings; writes need `SERVICE_MANAGE` |

### Customers, vehicles, directory
| Method | Path | Notes |
|---|---|---|
| GET/POST | `customers/` | agency (`CUSTOMER_VIEW` / `CUSTOMER_CREATE` walk-ins) · Super Admin |
| GET/PATCH | `customers/{id}/` | agencies edit only their own walk-ins |
| GET/POST | `customers/{id}/notes/` | tenant-private internal notes |
| GET | `customers/{id}/summary/` · `customers/{id}/timeline/` | agency-scoped figures & events |
| GET/PATCH | `customers/me/`; GET `customers/me/timeline/` | customer self-service |
| CRUD | `vehicles/`; GET/POST `vehicles/{id}/documents/`; DELETE `vehicles/{id}/documents/{doc}/` | DELETE vehicle = archive |
| GET | `vendors/` (`?service=<slug|id>&vehicle_type=CAR&city=&ordering=price`) · `vendors/{id}/` · `vendors/{id}/hours/` · `vendors/{id}/services/` | active agencies only, public fields |

### Availability & bookings
| Method | Path | Notes |
|---|---|---|
| GET | `availability/slots/?vendor_service=&date=YYYY-MM-DD` | backend-computed slots with `available`, `remaining`, `reason` |
| GET | `availability/days/?vendor_service=&start=&days=14` | per-day summary (≤31 days) |
| GET/POST | `bookings/` | customer: own · staff: assigned · managers/admins: agency (`BOOKING_VIEW`) |
| GET/PATCH | `bookings/{id}/` | PATCH: `customer_notes` (customer) / `internal_notes` (agency) |
| POST | `bookings/{id}/confirm|reject|receive-vehicle|start|complete|no-show/` | `BOOKING_UPDATE`; `{note}` |
| POST | `bookings/{id}/cancel/` `{reason}` · `bookings/{id}/reschedule/` `{start_datetime, reason}` · `bookings/{id}/assign/` `{staff, resource}` | |
| GET | `bookings/{id}/history/` · `bookings/calendar/?start=&end=` (≤62 days; `organization`, `service`, `status` filters) | |

`allowed_actions` on every booking tells the UI which buttons to show — the API still re-checks everything.

### Workshop
| Method | Path | Notes |
|---|---|---|
| GET | `job-cards/` · `job-cards/{id}/` | staff: assigned only · customer: own (read-only) |
| PATCH | `job-cards/{id}/` | odometer, fuel, damage, notes (`JOB_CARD_UPDATE`) |
| PUT | `job-cards/{id}/inspection/` | checklist upsert (BEFORE / AFTER) |
| POST | `job-cards/{id}/photos/` (multipart) · `…/start-work/` · `…/complete/` · `…/close/` | |
| POST | `job-cards/{id}/additional-work/` · `…/additional-work/{wid}/respond/` `{approve}` · `…/cancel/` | customer approves; auto-approve if configured |
| POST | `job-cards/{id}/parts/` `{part, quantity}` · `job-cards/{id}/parts/{usage}/return/` | stock + ledger in one transaction |
| GET/POST/PATCH | `inventory/parts/` (`?low_stock=true`) · POST `inventory/parts/{id}/move/` · GET `…/transactions/` | writes: Admin/Manager |

### Finance
| Method | Path | Notes |
|---|---|---|
| GET | `invoices/` · `invoices/{id}/` · `invoices/{id}/pdf/` | customer: own issued · agency: `INVOICE_VIEW` |
| PATCH | `invoices/{id}/` `{discount, notes}` | before any payment; audited |
| POST | `invoices/{id}/void/` · `invoices/generate/` `{booking}` | Admin / Manager |
| GET | `payments/` · `payments/{id}/` | |
| POST | `payments/pay/` `{invoice | payment, method: MOCK|CARD|UPI, idempotency_key, simulate?}` | customer; `payments` throttle |
| POST | `payments/record/` `{invoice, amount, method: CASH|BANK_TRANSFER, reference}` · `payments/{id}/refund/` `{amount?, reason}` | agency; refunds: Admin |

### Notifications, reports, search
| Method | Path | Notes |
|---|---|---|
| GET | `notifications/` (`?unread=1`) · `notifications/unread-count/`; POST `notifications/mark-read/` `{ids?}` | own in-app inbox |
| GET | `reports/dashboard/` (`date_from`, `date_to`, `organization`*, `vehicle_type`, `service`, `status`) | role-specific stats + chart series |
| GET | `reports/` · `reports/{name}/` (`?export=csv|xlsx`) | agency: `REPORT_VIEW` |
| GET | `search/?q=` | customers, vehicles, bookings, invoices, job cards, vendors — tenant-scoped; `search` throttle |

\* `organization` is honoured for Super Admins only; agency scope always comes from the session.

---
Built by Sahil Thakur.
