import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit_logs.models import AuditAction, AuditLog, ImmutableRecordError
from apps.audit_logs.services import REDACTED, AuditService, sanitize

pytestmark = pytest.mark.django_db


def test_sensitive_keys_are_redacted():
    data = sanitize({"email": "a@b.c", "password": "x", "nested": {"refresh_token": "t", "ok": 1},
                     "api_key": "k", "items": [{"secret": "s"}]})
    assert data == {"email": "a@b.c", "password": REDACTED, "nested": {"refresh_token": REDACTED, "ok": 1},
                    "api_key": REDACTED, "items": [{"secret": REDACTED}]}


def test_log_records_request_metadata(rf, customer):
    request = rf.post("/x", HTTP_USER_AGENT="pytest-agent", REMOTE_ADDR="10.1.2.3")
    request.user = customer
    log = AuditService.log(AuditAction.LOGIN, request=request, instance=customer)
    assert log.user == customer
    assert log.ip_address == "10.1.2.3"
    assert log.user_agent == "pytest-agent"
    assert log.model_name == "User" and log.object_id == str(customer.pk)


def test_x_forwarded_for_ignored_unless_trusted(rf, settings):
    request = rf.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1", REMOTE_ADDR="10.0.0.1")
    settings.TRUST_X_FORWARDED_FOR = False
    assert AuditService.log(AuditAction.LOGIN, request=request).ip_address == "10.0.0.1"
    settings.TRUST_X_FORWARDED_FOR = True
    assert AuditService.log(AuditAction.LOGIN, request=request).ip_address == "1.1.1.1"


def test_orm_prevents_update_and_delete():
    log = AuditService.log(AuditAction.LOGIN)
    log.action = AuditAction.LOGOUT
    with pytest.raises(ImmutableRecordError):
        log.save()
    with pytest.raises(ImmutableRecordError):
        log.delete()
    with pytest.raises(ImmutableRecordError):
        AuditLog.objects.all().update(action=AuditAction.LOGOUT)
    with pytest.raises(ImmutableRecordError):
        AuditLog.objects.all().delete()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="append-only trigger is PostgreSQL-only")
def test_database_trigger_blocks_raw_update_and_delete():
    log = AuditService.log(AuditAction.LOGIN)
    for sql in ("UPDATE audit_logs_auditlog SET action = 'LOGOUT' WHERE id = %s",
                "DELETE FROM audit_logs_auditlog WHERE id = %s"):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [log.id])
    assert AuditLog.objects.get(id=log.id).action == AuditAction.LOGIN


def test_super_admin_can_read_all_logs(auth_client, super_admin, agency_a, agency_b):
    AuditService.log(AuditAction.AGENCY_UPDATED, organization=agency_a.org)
    AuditService.log(AuditAction.AGENCY_UPDATED, organization=agency_b.org)
    res = auth_client(super_admin).get("/api/v1/audit-logs/?action=AGENCY_UPDATED")
    assert res.status_code == 200
    assert res.json()["meta"]["pagination"]["count"] == 2


def test_audit_log_api_is_read_only(auth_client, super_admin):
    log = AuditService.log(AuditAction.LOGIN)
    client = auth_client(super_admin)
    assert client.delete(f"/api/v1/audit-logs/{log.id}/").status_code == 405
    assert client.patch(f"/api/v1/audit-logs/{log.id}/", {"action": "LOGOUT"}).status_code == 405
