"""
Vercel (serverless) settings — Glideinbir, built by Sahil Thakur.

The React app is served by Vercel's CDN; Django runs as one Python function on the
same domain (so no CORS). Serverless means: no persistent disk (media → /tmp or S3),
no Redis (in-process cache, Celery tasks inline) and no Beat (Vercel Cron calls
/api/v1/internal/cron/reminders/ instead). PostgreSQL comes from the Neon integration.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, REST_FRAMEWORK, SIMPLE_JWT, STORAGES, env, tune_database

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in the Vercel project environment.")
if not SIMPLE_JWT["SIGNING_KEY"]:
    SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

_production_host = env("VERCEL_PROJECT_PRODUCTION_URL", default="")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[".vercel.app", "localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://*.vercel.app"])
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # same-origin SPA
FRONTEND_URL = env("FRONTEND_URL", default=f"https://{_production_host}" if _production_host else "")

# --- Database: Neon's pooled URL; no persistent connections in serverless ------------
_db_url = env("DATABASE_URL", default="") or env("POSTGRES_URL", default="")
if not _db_url:
    raise ImproperlyConfigured("Connect a PostgreSQL database (Neon integration) to provide DATABASE_URL.")
DATABASES = {"default": tune_database(env.db_url_config(_db_url))}
DATABASES["default"]["CONN_MAX_AGE"] = 0

# --- No Redis on Vercel ----------------------------------------------------------------
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "glideinbir"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CRON_SECRET = env("CRON_SECRET", default="")

# --- Static & media ----------------------------------------------------------------------
# WhiteNoise serves admin/Swagger assets straight from app directories (no collectstatic step).
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
WHITENOISE_USE_FINDERS = True
STATIC_ROOT = None  # nothing is collected on Vercel; WhiteNoise reads app static dirs
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
MEDIA_ROOT = env("MEDIA_ROOT", default="/tmp/glideinbir-media")
SERVE_MEDIA = True  # replaced by signed S3 URLs when USE_S3_STORAGE is on
if env.bool("USE_S3_STORAGE", default=False):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET_NAME"), "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "region_name": env("S3_REGION", default=None), "access_key": env("S3_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_ACCESS_KEY"), "default_acl": "private", "querystring_auth": True,
            "file_overwrite": False,
        },
    }
    SERVE_MEDIA = False

# --- Transport security (Vercel terminates TLS and forces HTTPS) --------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
TRUST_X_FORWARDED_FOR = True

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=True)
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["anon"] = env("THROTTLE_ANON", default="120/min")
