# Database

> Multi-Vendor Vehicle Service CRM — **built by Sahil Thakur**

PostgreSQL 16. All primary keys are UUIDs. All datetimes are timezone-aware (`USE_TZ=True`,
default zone `Asia/Kolkata`, stored in UTC).

## 1. Phase 1 — implemented tables

```mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : "has"
    ORGANIZATION ||--o{ MEMBERSHIP : "employs"
    USER ||--o{ AUDIT_LOG : "performed"
    ORGANIZATION ||--o{ AUDIT_LOG : "scoped to"
    USER ||--o{ OUTSTANDING_TOKEN : "JWT refresh"
    OUTSTANDING_TOKEN ||--o| BLACKLISTED_TOKEN : "revoked"

    USER {
        uuid id PK
        string email UK "unique, case-insensitive"
        string full_name
        string phone "indexed"
        string role "SUPER_ADMIN|AGENCY_ADMIN|AGENCY_MANAGER|AGENCY_STAFF|CUSTOMER"
        string profile_photo
        bool is_active
        bool email_verified
        datetime email_verified_at
        datetime last_login
        datetime date_joined
    }
    ORGANIZATION {
        uuid id PK
        string name
        string legal_name
        string slug UK
        string logo
        string registration_number
        string gst_number "GSTIN format"
        string phone
        string email
        string website
        text description
        text address
        string city
        string state
        string country
        string pincode
        decimal latitude "-90..90"
        decimal longitude "-180..180"
        string status "PENDING|ACTIVE|INACTIVE|SUSPENDED|REJECTED"
        string verification_status "UNVERIFIED|PENDING|VERIFIED|REJECTED"
        text status_reason
        datetime status_changed_at
    }
    MEMBERSHIP {
        uuid id PK
        uuid user_id FK
        uuid organization_id FK
        json permissions "staff permission codes"
        bool is_active
        uuid created_by_id FK
    }
    AUDIT_LOG {
        uuid id PK
        uuid user_id FK "nullable"
        uuid organization_id FK "nullable"
        string action
        string model_name
        string object_id
        json old_data
        json new_data
        inet ip_address
        string user_agent
        datetime created_at
    }
```

### Constraints & indexes

| Table | Constraint / index | Purpose |
|---|---|---|
| `accounts_user` | `UNIQUE(lower(email))` | Case-insensitive unique login |
| | `CHECK role IN (...)` | No invalid roles even via raw SQL |
| | index `phone`, `role` | Search / filtering |
| `organizations_organization` | `UNIQUE(slug)` | Public identifier |
| | `CHECK status`, `CHECK verification_status`, `CHECK lat/long range` | Data integrity |
| | index `(status)`, `(city, status)` | Admin filters; future "bookable agencies in city" lookup |
| `organizations_membership` | `UNIQUE(user, organization)` | No duplicates |
| | `UNIQUE(user) WHERE is_active` | **Exactly one active tenant per agency user** |
| | index `(organization, is_active)` | Member listing |
| `audit_logs_auditlog` | index `(organization, -created_at)`, `(user, -created_at)`, `(action, -created_at)`, `(model_name, object_id)` | Tenant-scoped timelines and object history |
| | **trigger** `audit_logs_auditlog_immutable` | Rejects every `UPDATE` / `DELETE` (append-only) |

FKs to `Organization` use `PROTECT` — tenants are suspended/deactivated, never deleted.
Audit log FKs use `PROTECT` for the same reason (and the trigger would block `SET NULL` anyway).

## 2. Full platform ERD (target design for Phases 2–11)

```mermaid
erDiagram
    ORGANIZATION ||--o{ MEMBERSHIP : ""
    USER ||--o{ MEMBERSHIP : ""
    ORGANIZATION ||--o{ WORKING_HOURS : ""
    ORGANIZATION ||--o{ HOLIDAY : ""
    ORGANIZATION ||--o{ SERVICE_RESOURCE : ""
    ORGANIZATION ||--o{ VENDOR_SERVICE : "offers"
    SERVICE ||--o{ VENDOR_SERVICE : ""
    USER ||--o| CUSTOMER : "profile"
    CUSTOMER ||--o{ VEHICLE : "owns"
    CUSTOMER ||--o{ BOOKING : ""
    VEHICLE ||--o{ BOOKING : ""
    ORGANIZATION ||--o{ BOOKING : ""
    VENDOR_SERVICE ||--o{ BOOKING : ""
    SERVICE_RESOURCE ||--o{ BOOKING : "assigned_resource"
    USER ||--o{ BOOKING : "assigned_staff"
    BOOKING ||--o| JOB_CARD : ""
    JOB_CARD ||--o{ INSPECTION_ITEM : ""
    JOB_CARD ||--o{ JOB_PHOTO : ""
    JOB_CARD ||--o{ ADDITIONAL_WORK_REQUEST : ""
    ORGANIZATION ||--o{ PART : ""
    PART ||--o{ STOCK_TRANSACTION : ""
    JOB_CARD ||--o{ STOCK_TRANSACTION : "USED_IN_JOB"
    BOOKING ||--o{ INVOICE : ""
    INVOICE ||--o{ INVOICE_ITEM : ""
    INVOICE ||--o{ PAYMENT : ""
    BOOKING ||--o{ PAYMENT : ""
    USER ||--o{ NOTIFICATION : ""
    ORGANIZATION ||--o{ AUDIT_LOG : ""

    SERVICE {
        uuid id PK
        string name
        string slug UK
        string category
        json supported_vehicle_types
        int default_duration
        decimal base_price
        decimal tax
        bool active
    }
    VENDOR_SERVICE {
        uuid id PK
        uuid organization_id FK
        uuid service_id FK
        decimal custom_price
        int custom_duration
        int capacity
        bool active
        bool online_booking_enabled
    }
    CUSTOMER {
        uuid id PK
        uuid user_id FK
        string full_name
        string phone
        string email
        string city
    }
    VEHICLE {
        uuid id PK
        uuid customer_id FK
        string vehicle_type
        string brand
        string model
        string registration_number
        string vin
        date insurance_expiry
    }
    BOOKING {
        uuid id PK
        string booking_number UK
        uuid organization_id FK
        uuid vendor_service_id FK
        datetime start_datetime
        datetime end_datetime
        string status
        string payment_status
    }
    JOB_CARD {
        uuid id PK
        string job_card_number UK
        uuid booking_id FK
        string status
        int odometer
        string fuel_level
    }
    INVOICE {
        uuid id PK
        string invoice_number UK
        uuid organization_id FK
        decimal subtotal
        decimal tax
        decimal total
        string payment_status
    }
    PAYMENT {
        uuid id PK
        uuid invoice_id FK
        decimal amount
        string method
        string status
        string transaction_id
    }
```

Design notes for later phases:

* Every tenant-owned table inherits `TenantModel` (`organization_id` + `TenantManager`).
* Booking double-booking prevention: `select_for_update()` on the `VendorService`/resource rows inside
  `transaction.atomic()`, conflict + capacity checks repeated inside the lock, plus a PostgreSQL
  exclusion constraint (`btree_gist`, `tstzrange(start, end) &&`) on `assigned_resource` where applicable.
* Human-readable numbers (`BK-2026-000001`, `JOB-…`, `INV-…`) come from a per-prefix/year counter row
  locked with `select_for_update`, not from `MAX()+1`.
* Customers are platform-level users; an agency "sees" a customer only through that customer's bookings
  with the agency, so customer data stays tenant-scoped.

## 3. Migrations

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run   # CI guard
```

---
Built by Sahil Thakur.
