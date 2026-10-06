"""
Local development. Works with zero infrastructure:

* no ``DATABASE_URL`` → SQLite file ``backend/dev.sqlite3``
* no ``REDIS_URL``    → in-process cache, Celery tasks run inline, ``run_scheduler`` replaces Celery Beat

Set ``DATABASE_URL`` / ``REDIS_URL`` (Docker does) to use PostgreSQL and Redis instead.
"""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, REST_FRAMEWORK, SIMPLE_JWT, env, tune_database

DEBUG = env.bool("DJANGO_DEBUG", default=True)

if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "dev-insecure-only-for-local-development-change-me"

if not SIMPLE_JWT["SIGNING_KEY"]:
    SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0", "backend"])

if not env("DATABASE_URL", default=""):
    DATABASES = {"default": tune_database({"ENGINE": "django.db.backends.sqlite3",
                                           "NAME": str(BASE_DIR / "dev.sqlite3")})}

NO_REDIS = not env("REDIS_URL", default="") and not env("CACHE_URL", default="")
if NO_REDIS:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "crm-dev"}}
    CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
    CELERY_TASK_EAGER_PROPAGATES = False
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    # One process, one in-memory throttle store — keep login limits friendly for local testing.
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth"] = env("THROTTLE_AUTH", default="30/min")
