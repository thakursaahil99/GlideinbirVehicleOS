"""
Base settings shared by every environment.

Vehicle Service CRM — built by Sahil Thakur.
All secrets and environment-specific values come from environment variables.
"""
from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load the repo-root .env when running outside Docker; real env vars win.
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file), overwrite=False)

# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

PROJECT_NAME = "Vehicle Service CRM"
PROJECT_AUTHOR = "Sahil Thakur"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.audit_logs",
    "apps.vendors",
    "apps.customers",
    "apps.vehicles",
    "apps.services",
    "apps.bookings",
    "apps.availability",
    "apps.job_cards",
    "apps.inventory",
    "apps.payments",
    "apps.invoices",
    "apps.notifications",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def tune_database(db):
    """
    Connection settings per engine. SQLite (local runs without Docker/PostgreSQL)
    gets IMMEDIATE transactions — writers queue on the database lock instead of
    racing, which is how booking capacity stays safe without row locks — plus WAL
    so readers never block, and a busy timeout instead of "database is locked".
    """
    db["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    db["CONN_HEALTH_CHECKS"] = True
    if db["ENGINE"] == "django.db.backends.sqlite3":
        db["CONN_MAX_AGE"] = 0
        db.setdefault("OPTIONS", {}).update({
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=20000;",
        })
    return db


DATABASES = {
    "default": tune_database(env.db("DATABASE_URL", default="postgres://crm:crm@localhost:5432/crm")),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=60 * 60 * 2)  # 2 hours

# --------------------------------------------------------------------------- #
# I18N / timezone
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Static & media (local storage behind an S3-compatible abstraction)
# --------------------------------------------------------------------------- #
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

USE_S3_STORAGE = env.bool("USE_S3_STORAGE", default=False)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Upload limits (per-file rules live in apps.core.validators)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = env.int("MAX_IMAGE_UPLOAD_BYTES", default=5 * 1024 * 1024)

# --------------------------------------------------------------------------- #
# Cache (Redis). Never cache tenant data under a key without the tenant id.
# --------------------------------------------------------------------------- #
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHE_URL = env("CACHE_URL", default=REDIS_URL.rsplit("/", 1)[0] + "/1")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CACHE_URL,
        "KEY_PREFIX": "crm",
        "TIMEOUT": 300,
    }
}
if CACHE_URL.startswith("locmem://"):  # local runs without Redis (single process only)
    CACHES["default"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}

# --------------------------------------------------------------------------- #
# Django REST Framework
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("apps.core.renderers.EnvelopeJSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="300/min"),
        "auth": env("THROTTLE_AUTH", default="10/min"),
        "payments": env("THROTTLE_PAYMENTS", default="20/min"),
        "search": env("THROTTLE_SEARCH", default="60/min"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # handled by AuthService so it is audited
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default="") or None,  # falls back to SECRET_KEY below
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Vehicle Service CRM API",
    "DESCRIPTION": (
        "Multi-vendor vehicle service CRM — versioned REST API (/api/v1/). "
        "Authenticate with `Authorization: Bearer <access token>`. "
        "Every response uses the envelope `{success, data}` or `{success, error}`. "
        "Built by Sahil Thakur."
    ),
    "VERSION": "1.0.0",
    "CONTACT": {"name": "Sahil Thakur"},
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    # Stable, readable enum names for clients generated from the schema.
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": "apps.accounts.constants.Role",
        "AgencyRoleEnum": ["AGENCY_MANAGER", "AGENCY_STAFF", "AGENCY_ADMIN"],
        "OrganizationStatusEnum": "apps.organizations.models.OrganizationStatus",
        "VerificationStatusEnum": "apps.organizations.models.VerificationStatus",
        "BookingStatusEnum": "apps.bookings.models.BookingStatus",
        "BookingPaymentStatusEnum": "apps.bookings.models.PaymentStatus",
        "JobCardStatusEnum": "apps.job_cards.models.JobCardStatus",
        "AdditionalWorkStatusEnum": "apps.job_cards.models.AdditionalWorkStatus",
        "InspectionStageEnum": "apps.job_cards.models.InspectionStage",
        "PhotoStageEnum": "apps.job_cards.models.PhotoStage",
        "PaymentRecordStatusEnum": "apps.payments.models.PaymentRecordStatus",
        "InvoiceStatusEnum": "apps.invoices.models.InvoiceStatus",
        "VehicleTypeEnum": "apps.vehicles.models.VehicleType",
        "ResourceTypeEnum": "apps.vendors.models.ResourceType",
        "DeliveryStatusEnum": "apps.notifications.models.DeliveryStatus",
    },
}

# --------------------------------------------------------------------------- #
# CORS / CSRF
# --------------------------------------------------------------------------- #
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
CORS_ALLOW_CREDENTIALS = False  # JWT in Authorization header, no cookies
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173"])

# --------------------------------------------------------------------------- #
# Security headers (prod.py tightens transport security further)
# --------------------------------------------------------------------------- #
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
# Only trust X-Forwarded-For when running behind a known reverse proxy.
TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)

# --------------------------------------------------------------------------- #
# Email (console backend in development)
# --------------------------------------------------------------------------- #
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Vehicle Service CRM <no-reply@vehicle-crm.local>")
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")

# --------------------------------------------------------------------------- #
# Celery
# --------------------------------------------------------------------------- #
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)  # local runs without Redis
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_BEAT_SCHEDULE = {
    "cleanup-expired-tokens": {
        "task": "apps.accounts.tasks.cleanup_expired_tokens",
        "schedule": crontab(hour=3, minute=0),
    },
    "send-booking-reminders": {
        "task": "apps.notifications.tasks.send_booking_reminder",
        "schedule": crontab(minute="*/15"),
    },
}

# --------------------------------------------------------------------------- #
# Integrations (mocked in development; swap dotted paths for real providers)
# --------------------------------------------------------------------------- #
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="apps.payments.providers.MockPaymentProvider")
NOTIFICATION_PROVIDERS = {
    "EMAIL": env("NOTIFY_EMAIL_PROVIDER", default="apps.notifications.providers.EmailProvider"),
    "SMS": env("NOTIFY_SMS_PROVIDER", default="apps.notifications.providers.MockSMSProvider"),
    "WHATSAPP": env("NOTIFY_WHATSAPP_PROVIDER", default="apps.notifications.providers.MockWhatsAppProvider"),
}

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}

DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", default="django-admin/")
API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
