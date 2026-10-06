import re

import pytest
from django.core import mail

from apps.accounts.constants import Role
from apps.accounts.models import User
from apps.accounts.tokens import encode_uid, password_reset_token
from apps.audit_logs.models import AuditAction, AuditLog

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"


def login(client, email, password=PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password})


class TestRegistration:
    def test_customer_can_register_and_gets_tokens(self, api_client, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = api_client.post(REGISTER, {"email": "New@Example.com", "password": PASSWORD,
                                             "full_name": "New Person", "phone": "+919876543210"})
        assert res.status_code == 201, res.json()
        body = res.json()
        assert body["success"] is True
        assert body["data"]["user"]["role"] == Role.CUSTOMER
        assert body["data"]["user"]["email"] == "new@example.com"
        assert {"access", "refresh"} <= body["data"]["tokens"].keys()
        assert len(mail.outbox) == 1 and "Verify" in mail.outbox[0].subject
        assert AuditLog.objects.filter(action=AuditAction.USER_CREATED).exists()

    def test_registration_cannot_choose_role(self, api_client):
        res = api_client.post(REGISTER, {"email": "x@example.com", "password": PASSWORD, "full_name": "X",
                                         "role": Role.SUPER_ADMIN})
        assert res.status_code == 201
        assert User.objects.get(email="x@example.com").role == Role.CUSTOMER

    def test_duplicate_email_is_case_insensitive(self, api_client, make_user):
        make_user(email="dup@example.com")
        res = api_client.post(REGISTER, {"email": "DUP@example.com", "password": PASSWORD, "full_name": "D"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "email" in res.json()["error"]["details"]

    def test_weak_password_rejected(self, api_client):
        res = api_client.post(REGISTER, {"email": "w@example.com", "password": "12345678", "full_name": "W"})
        assert res.status_code == 400
        assert "password" in res.json()["error"]["details"]


class TestLogin:
    def test_login_success_returns_user_and_tokens(self, api_client, customer):
        res = login(api_client, customer.email)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["user"]["id"] == str(customer.id)
        customer.refresh_from_db()
        assert customer.last_login is not None
        assert AuditLog.objects.filter(action=AuditAction.LOGIN, user=customer).exists()

    def test_wrong_password(self, api_client, customer):
        res = login(api_client, customer.email, "wrong-password")
        assert res.status_code == 401
        assert res.json() == {"success": False, "error": {"code": "INVALID_CREDENTIALS",
                                                          "message": "Invalid email or password."}}
        log = AuditLog.objects.get(action=AuditAction.LOGIN_FAILED)
        assert "wrong-password" not in str(log.new_data)

    def test_unknown_email_same_error(self, api_client):
        res = login(api_client, "ghost@example.com")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_inactive_user_cannot_login(self, api_client, make_user):
        user = make_user(is_active=False)
        assert login(api_client, user.email).status_code == 401

    def test_email_login_is_case_insensitive(self, api_client, customer):
        assert login(api_client, customer.email.upper()).status_code == 200

    def test_login_is_rate_limited(self, api_client, customer, monkeypatch):
        from apps.accounts.views import AuthRateThrottle

        monkeypatch.setattr(AuthRateThrottle, "THROTTLE_RATES", {"auth": "3/min"})
        codes = [login(api_client, customer.email, "bad").status_code for _ in range(4)]
        assert codes[:3] == [401, 401, 401]
        assert codes[3] == 429


class TestTokens:
    def test_me_requires_auth(self, api_client):
        res = api_client.get(ME)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "NOT_AUTHENTICATED"

    def test_invalid_access_token(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        res = api_client.get(ME)
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "TOKEN_INVALID"

    def test_refresh_rotates_and_blacklists_old_token(self, api_client, customer):
        tokens = login(api_client, customer.email).json()["data"]["tokens"]
        res = api_client.post(REFRESH, {"refresh": tokens["refresh"]})
        assert res.status_code == 200
        new = res.json()["data"]
        assert new["refresh"] != tokens["refresh"]
        # The old refresh token is blacklisted after rotation.
        reuse = api_client.post(REFRESH, {"refresh": tokens["refresh"]})
        assert reuse.status_code == 401

    def test_logout_blacklists_refresh_token(self, api_client, customer):
        tokens = login(api_client, customer.email).json()["data"]["tokens"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        res = api_client.post(LOGOUT, {"refresh": tokens["refresh"]})
        assert res.status_code == 200
        assert api_client.post(REFRESH, {"refresh": tokens["refresh"]}).status_code == 401
        assert AuditLog.objects.filter(action=AuditAction.LOGOUT, user=customer).exists()

    def test_cannot_logout_someone_elses_token(self, api_client, auth_client, make_user):
        victim, attacker = make_user(), make_user()
        victim_refresh = login(api_client, victim.email).json()["data"]["tokens"]["refresh"]
        res = auth_client(attacker).post(LOGOUT, {"refresh": victim_refresh})
        assert res.status_code == 400
        assert api_client.post(REFRESH, {"refresh": victim_refresh}).status_code == 200

    def test_deactivated_user_cannot_refresh(self, api_client, customer):
        refresh = login(api_client, customer.email).json()["data"]["tokens"]["refresh"]
        customer.is_active = False
        customer.save()
        assert api_client.post(REFRESH, {"refresh": refresh}).status_code == 401

    def test_deactivated_user_access_token_rejected(self, auth_client, customer):
        client = auth_client(customer)
        customer.is_active = False
        customer.save()
        assert client.get(ME).status_code == 401


class TestProfileAndPasswords:
    def test_me_returns_profile(self, auth_client, customer):
        res = auth_client(customer).get(ME)
        assert res.status_code == 200
        assert res.json()["data"]["email"] == customer.email
        assert res.json()["data"]["organization"] is None

    def test_me_for_agency_user_includes_organization(self, auth_client, agency_a):
        data = auth_client(agency_a.staff).get(ME).json()["data"]
        assert data["organization"]["id"] == str(agency_a.org.id)
        assert "BOOKING_VIEW" in data["permissions"]

    def test_update_profile_cannot_change_role_or_email(self, auth_client, customer):
        res = auth_client(customer).patch(ME, {"full_name": "Renamed", "role": Role.SUPER_ADMIN,
                                               "email": "evil@example.com"})
        assert res.status_code == 200
        customer.refresh_from_db()
        assert customer.full_name == "Renamed"
        assert customer.role == Role.CUSTOMER
        assert customer.email != "evil@example.com"

    def test_change_password_revokes_refresh_tokens(self, api_client, auth_client, customer):
        refresh = login(api_client, customer.email).json()["data"]["tokens"]["refresh"]
        res = auth_client(customer).post("/api/v1/auth/change-password/",
                                         {"current_password": PASSWORD, "new_password": "An0ther!Secret9"})
        assert res.status_code == 200
        assert api_client.post(REFRESH, {"refresh": refresh}).status_code == 401
        assert login(api_client, customer.email, "An0ther!Secret9").status_code == 200

    def test_change_password_wrong_current(self, auth_client, customer):
        res = auth_client(customer).post("/api/v1/auth/change-password/",
                                         {"current_password": "nope", "new_password": "An0ther!Secret9"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_PASSWORD"

    def test_password_reset_flow(self, api_client, customer, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = api_client.post("/api/v1/auth/password-reset/", {"email": customer.email})
        assert res.status_code == 200
        assert len(mail.outbox) == 1
        match = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[0].body)
        uid, token = match.groups()

        res = api_client.post("/api/v1/auth/password-reset/confirm/",
                              {"uid": uid, "token": token, "new_password": "Brand!New9Pass"})
        assert res.status_code == 200
        assert login(api_client, customer.email, "Brand!New9Pass").status_code == 200
        # Token is single-use: the password hash changed.
        again = api_client.post("/api/v1/auth/password-reset/confirm/",
                                {"uid": uid, "token": token, "new_password": "Other!New9Pass"})
        assert again.status_code == 400
        assert again.json()["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"

    def test_password_reset_does_not_reveal_unknown_email(self, api_client):
        res = api_client.post("/api/v1/auth/password-reset/", {"email": "nobody@example.com"})
        assert res.status_code == 200
        assert len(mail.outbox) == 0

    def test_password_reset_bad_uid(self, api_client):
        res = api_client.post("/api/v1/auth/password-reset/confirm/",
                              {"uid": "garbage", "token": "x", "new_password": "Brand!New9Pass"})
        assert res.status_code == 400

    def test_email_verification_flow(self, api_client, customer):
        from apps.accounts.tokens import email_verification_token

        payload = {"uid": encode_uid(customer), "token": email_verification_token.make_token(customer)}
        assert api_client.post("/api/v1/auth/verify-email/", payload).status_code == 200
        customer.refresh_from_db()
        assert customer.email_verified and customer.email_verified_at
        # Single use.
        assert api_client.post("/api/v1/auth/verify-email/", payload).status_code == 400

    def test_password_reset_token_cannot_verify_email(self, api_client, customer):
        payload = {"uid": encode_uid(customer), "token": password_reset_token.make_token(customer)}
        assert api_client.post("/api/v1/auth/verify-email/", payload).status_code == 400
