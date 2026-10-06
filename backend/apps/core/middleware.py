from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Extra response headers Django doesn't set itself.

    API responses are JSON (or file downloads) and never need scripts, styles or
    framing, so they get the strictest possible Content-Security-Policy. The
    Swagger UI and Django admin keep their own needs and are left alone.
    """

    API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

    def __init__(self, get_response):
        self.get_response = get_response
        self.docs_prefix = "/api/v1/docs"

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(self)")
        response.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if request.path.startswith("/api/") and not request.path.startswith(self.docs_prefix):
            response.setdefault("Content-Security-Policy", self.API_CSP)
            # Authenticated API data must never be stored by shared caches.
            if getattr(request, "user", None) is not None and request.META.get("HTTP_AUTHORIZATION"):
                response.setdefault("Cache-Control", "no-store")
        if settings.DEBUG is False:
            response.headers.pop("Server", None)
        return response
