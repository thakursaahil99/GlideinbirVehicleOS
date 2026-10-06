import pytest

pytestmark = pytest.mark.django_db


def test_health_endpoint(api_client):
    res = api_client.get("/api/v1/health/")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["database"] == "ok"
    assert body["data"]["built_by"] == "Sahil Thakur"


def test_paginated_envelope(auth_client, super_admin):
    body = auth_client(super_admin).get("/api/v1/users/").json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert {"count", "page", "page_size", "total_pages", "next", "previous"} <= body["meta"]["pagination"].keys()


def test_unknown_route_returns_json_404(api_client):
    res = api_client.get("/api/v1/does-not-exist/")
    assert res.status_code == 404
    assert res.json() == {"success": False,
                          "error": {"code": "NOT_FOUND", "message": "The requested resource was not found."}}


def test_unhandled_exception_hides_stack_trace(auth_client, super_admin, monkeypatch):
    from apps.accounts import views

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(views.MeView, "get", boom)
    res = auth_client(super_admin).get("/api/v1/auth/me/")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in res.content.decode()


def test_security_headers(api_client):
    res = api_client.get("/api/v1/health/")
    assert res["X-Content-Type-Options"] == "nosniff"
    assert res["X-Frame-Options"] == "DENY"
    assert res["Referrer-Policy"] == "same-origin"


def test_openapi_schema_is_generated(api_client):
    res = api_client.get("/api/v1/schema/?format=json")
    assert res.status_code == 200
    schema = res.json()
    assert "Sahil Thakur" in schema["info"]["description"]
    assert "/api/v1/auth/login/" in schema["paths"]


def test_timezone_settings(settings):
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "Asia/Kolkata"
