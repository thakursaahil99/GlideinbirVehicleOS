from .base import *  # noqa: F401,F403
from .base import BASE_DIR, REST_FRAMEWORK, SIMPLE_JWT, env, tune_database

# `pytest` works out of the box on SQLite; set DATABASE_URL to run on PostgreSQL (CI does).
if not env("DATABASE_URL", default=""):
    DATABASES = {"default": tune_database({"ENGINE": "django.db.backends.sqlite3",
                                           "NAME": str(BASE_DIR / "test.sqlite3")})}
    # A real file (not :memory:) so threaded concurrency tests use independent connections.
    DATABASES["default"]["TEST"] = {"NAME": str(BASE_DIR / "test_db.sqlite3")}

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

# Fast hashing for tests only.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"anon": "10000/min", "user": "10000/min", "auth": "10000/min",
                                            "payments": "10000/min", "search": "10000/min"}

MEDIA_ROOT = BASE_DIR / "test-media"  # noqa: F405
