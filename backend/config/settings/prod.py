from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, SIMPLE_JWT, STORAGES, USE_S3_STORAGE, env

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong value in production.")

if not SIMPLE_JWT["SIGNING_KEY"]:
    SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
# Container health probes call the app on localhost from inside the network.
ALLOWED_HOSTS += [h for h in ("localhost", "127.0.0.1") if h not in ALLOWED_HOSTS]

# Serve static assets (admin, API docs) efficiently.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}

if USE_S3_STORAGE:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET_NAME"),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "region_name": env("S3_REGION", default=None),
            "access_key": env("S3_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_ACCESS_KEY"),
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }

# Transport security
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]  # internal health probes speak plain HTTP
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

API_DOCS_ENABLED = env.bool("API_DOCS_ENABLED", default=False)
