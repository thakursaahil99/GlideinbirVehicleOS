import json
import logging

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.fields.files import FieldFile
from django.forms.models import model_to_dict

from .models import AuditLog

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
_SENSITIVE_FRAGMENTS = ("password", "token", "secret", "api_key", "apikey", "access", "refresh",
                        "authorization", "otp", "pin_code", "cvv", "card_number")


def _is_sensitive(key):
    key = str(key).lower()
    return any(fragment in key for fragment in _SENSITIVE_FRAGMENTS)


def sanitize(data):
    """Drop secrets and coerce values to JSON-safe primitives."""
    if data is None:
        return None
    if isinstance(data, dict):
        return {str(k): (REDACTED if _is_sensitive(k) else sanitize(v)) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [sanitize(v) for v in data]
    if isinstance(data, (str, int, float, bool)):
        return data
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder, default=str))


def snapshot(instance, fields=None):
    """A JSON-safe dict of selected model fields, for old_data/new_data."""
    data = model_to_dict(instance, fields=fields)
    for key, value in list(data.items()):
        if isinstance(value, FieldFile):
            data[key] = value.name or None
    return sanitize(data)


def diff(old, new):
    """Return (old_subset, new_subset) containing only keys whose values changed."""
    changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    return {k: old.get(k) for k in changed}, {k: new.get(k) for k in changed}


def client_ip(request):
    if request is None:
        return None
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


class AuditService:
    @staticmethod
    def log(action, *, user=None, organization=None, instance=None, model_name="", object_id="",
            old_data=None, new_data=None, request=None):
        if user is None and request is not None and getattr(request, "user", None) is not None:
            if request.user.is_authenticated:
                user = request.user
        if instance is not None:
            model_name = model_name or instance.__class__.__name__
            object_id = object_id or str(instance.pk)
        return AuditLog.objects.create(
            user=user,
            organization=organization,
            action=action,
            model_name=model_name,
            object_id=str(object_id or ""),
            old_data=sanitize(old_data),
            new_data=sanitize(new_data),
            ip_address=client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:512] if request is not None else ""),
        )
