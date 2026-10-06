# Glideinbir — Vehicle Operating System

**Multi-vendor, multi-tenant SaaS for vehicle service agencies — built by Sahil Thakur.**

Independent workshops (agencies) manage bookings, customers, vehicles, job cards, inventory, payments and
invoices for cars, bikes, scooters and EVs, while a Super Admin oversees the platform. Every agency's data is
strictly isolated.

> **Status: all 13 phases built** — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#8-roadmap).
>
> **Live demo:** https://glideinbir-vos.vercel.app — demo logins below (password `Demo@12345`); the Super Admin password is private.

## What's inside

| Area | Highlights |
|---|---|
| Tenancy & security | Server-side tenant resolution, 403/404 isolation sweeps over every object type, JWT rotation + blacklist, Argon2, audit trail with DB-level immutability, scoped throttles, strict CSP |
| Agencies | Approval workflow, staff invites with granular permission codes, split-shift working hours, holidays, special days, bays/technicians, booking rules |
| Customers & vehicles | Self-registered and walk-in customers, tenant-private notes, vehicles with RC/insurance/PUC documents and expiry alerts |
| Services | Global catalog (17 services seeded) + per-agency price, duration, capacity, pickup/drop; side-by-side price comparison |
| Availability & bookings | Backend-computed slots (hours, breaks, holidays, buffer, lead time, capacity, resources); row-locked booking with a PostgreSQL exclusion constraint; concurrency-tested; cancel/reschedule with history; day/week/month calendar |
| Workshop | Job cards, before/after inspection checklist and photos, customer-approved additional work, parts consumption with a stock ledger |
| Finance | Auto-generated GST invoices with PDF, mock payment gateway (UPI/card), cash/bank receipts, refunds, idempotent payments |
| Notifications | In-app inbox + e-mail / SMS / WhatsApp (mocked) via Celery, booking reminders via Celery Beat |
| Insight | Role dashboards with charts, 13 reports with CSV/Excel export, global search, customer timeline |

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework, django-filter, drf-spectacular, Pillow |
| Auth | JWT (simplejwt) with rotation + blacklisting, Argon2 hashing |
| Database | PostgreSQL 16 |
| Async / cache | Redis 7, Celery, Celery Beat |
| Testing | pytest, pytest-django |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router 7, TanStack Query, React Hook Form, Zod |
| DevOps | Docker, Docker Compose |

Everything is free and open source. E-mail uses Django's console backend in development; SMS, WhatsApp and
payment providers will be mocked behind interfaces.

## Quick start (no Docker needed)

Needs only **Python 3.12** (or [uv](https://docs.astral.sh/uv/)) and **Node.js 20.19+**. No PostgreSQL, Redis or Docker.

```powershell
setup.bat        # one time: virtualenv, packages, database, demo data, npm install   (or .\scripts\setup.ps1)
start.bat        # opens 3 windows: API :8000, job scheduler, web app :5173            (or .\scripts\start.ps1)
```

Then open **http://localhost:5173**. Options: `.\scripts\setup.ps1 -Fresh` (empty database), `-NoSeed`;
`.\scripts\start.ps1 -BackendPort 8001 -FrontendPort 5174` if the ports are busy.

How it runs without infrastructure (all automatic when `DATABASE_URL` / `REDIS_URL` aren't set):

| Normally | Without Docker |
|---|---|
| PostgreSQL | SQLite file `backend/dev.sqlite3` in WAL mode with `BEGIN IMMEDIATE` transactions, so bookings are serialized — the concurrent double-booking tests pass on it too |
| Redis cache / throttling | in-process memory cache |
| Celery worker | tasks run inline (e-mails print in the API window) |
| Celery Beat | `python manage.py run_scheduler` (the 3rd window): reminders every 15 min, nightly token cleanup |

Manual equivalent:

```bash
cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements/dev.txt
.venv\Scripts\python manage.py migrate && .venv\Scripts\python manage.py seed_demo_data
.venv\Scripts\python manage.py runserver          # terminal 1
.venv\Scripts\python manage.py run_scheduler      # terminal 2
cd frontend && npm install && npm run dev          # terminal 3
```

Tests: `cd backend && .venv\Scripts\python -m pytest` (SQLite by default; set `DATABASE_URL` for PostgreSQL — CI does).
Want real PostgreSQL/Redis without Docker? Install them natively and set `DATABASE_URL` / `REDIS_URL` in `.env`;
then run `celery -A config worker` and `celery -A config beat` instead of `run_scheduler`.

Demo accounts (password `Demo@12345`):

| Role | E-mail |
|---|---|
| Super Admin | `superadmin@demo.local` |
| Agency Admin | `admin@speedy-auto-care.demo.local` |
| Agency Manager | `manager@speedy-auto-care.demo.local` |
| Agency Staff | `staff@speedy-auto-care.demo.local` |
| Customer | `customer01@demo.local` … `customer20@demo.local` |

"Royal Bikes Workshop" is seeded as **PENDING** so you can try the approval flow.

Create your own Super Admin with `docker compose exec backend python manage.py createsuperuser`.

## With Docker (PostgreSQL + Redis + Celery)

```bash
cp .env.example .env                 # adjust if needed
docker compose up --build            # postgres, redis, backend, celery, celery-beat, frontend
docker compose exec backend python manage.py seed_demo_data
```

| URL | What |
|---|---|
| http://localhost:5173 | Web app |
| http://localhost:8000/api/v1/docs/ | Swagger UI |
| http://localhost:8000/api/v1/health/ | Health check |
| http://localhost:8000/django-admin/ | Django admin |

### Docker commands

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations
docker compose exec backend pytest                      # full test suite (PostgreSQL)
docker compose exec backend pytest --cov=apps           # with coverage
docker compose logs -f celery                           # e-mails (console backend) appear here
docker compose exec frontend npm run typecheck
```

Production: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` — see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Environment variables

All configuration comes from the environment; see [.env.example](.env.example) for the full list. Key ones:

| Variable | Default (dev) | Notes |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | `prod` in production |
| `DJANGO_SECRET_KEY` | dev placeholder | **Required** in production |
| `DATABASE_URL` | built by compose | `postgres://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://redis:6379/0` | broker + cache |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | 15 / 7 | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | |
| `FRONTEND_URL` | `http://localhost:5173` | used in e-mailed links |
| `THROTTLE_AUTH` | `10/min` | login / register / reset |
| `USE_S3_STORAGE` | `False` | S3-compatible media in production |

## Project structure

```
├── backend/
│   ├── config/            settings (base/dev/test/prod), urls, celery, wsgi/asgi
│   ├── apps/              core · accounts · organizations · audit_logs · vendors · customers · vehicles · services
│   │                      availability · bookings · job_cards · inventory · payments · invoices · notifications · reports
│   ├── requirements/      base / dev / prod
│   └── tests/             pytest suite
├── frontend/src/          api · components · layouts · pages · hooks · forms · types · utils · routes · stores
├── docker/                backend, frontend (dev + prod) Dockerfiles, nginx config
├── docker-compose.prod.yml  production-style stack (gunicorn, celery, nginx)
├── .github/workflows/ci.yml
├── docs/                  ARCHITECTURE · DATABASE · API · SECURITY · DEPLOYMENT
├── docker-compose.yml
└── .env.example
```

## Documentation

* [Architecture](docs/ARCHITECTURE.md): system design, apps, auth, multi-tenancy, permissions, Docker, roadmap
* [Database](docs/DATABASE.md): ERD (Mermaid), constraints, indexes
* [API](docs/API.md): envelope, error codes, endpoints
* [Security](docs/SECURITY.md)
* [Deployment](docs/DEPLOYMENT.md)

---

<p align="center"><b>Built by Sahil Thakur</b></p>
