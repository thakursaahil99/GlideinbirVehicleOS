"""
Domain exceptions and the global DRF exception handler.

Every error leaves the API as::

    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}

Unhandled exceptions are logged and returned as a generic INTERNAL_ERROR so
stack traces never reach clients.
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class AppError(exceptions.APIException):
    """Base class for business errors with a stable machine-readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"
    default_detail = "The request could not be processed."

    def __init__(self, message=None, *, code=None, details=None, status_code=None):
        super().__init__(detail=message or self.default_detail)
        if code:
            self.error_code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class InvalidCredentials(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "INVALID_CREDENTIALS"
    default_detail = "Invalid email or password."


class InvalidToken(AppError):
    error_code = "INVALID_OR_EXPIRED_TOKEN"
    default_detail = "The link is invalid or has expired."


class InvalidStateTransition(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "INVALID_STATE_TRANSITION"
    default_detail = "This action is not allowed in the current state."


class BusinessRuleViolation(AppError):
    error_code = "BUSINESS_RULE_VIOLATION"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"
    default_detail = "The resource was modified by another request."


# DRF default codes that we expose under a clearer name.
_CODE_OVERRIDES = {
    "invalid": "VALIDATION_ERROR",
    "throttled": "RATE_LIMITED",
    "token_not_valid": "TOKEN_INVALID",
    "error": "BAD_REQUEST",
}

_DEFAULT_MESSAGES = {
    "VALIDATION_ERROR": "Invalid input.",
}


def error_payload(code, message, details=None):
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"success": False, "error": error}


def _message_from_detail(detail):
    if isinstance(detail, dict):
        if "detail" in detail:
            return str(detail["detail"])
        return None
    if isinstance(detail, list):
        return str(detail[0]) if detail else None
    return str(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    elif isinstance(exc, (ProtectedError, RestrictedError)):
        exc = ConflictError("This record is in use and cannot be deleted. Deactivate it instead.",
                            code="RESOURCE_IN_USE")

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API exception", exc_info=exc)
        return Response(
            error_payload("INTERNAL_ERROR", "An unexpected error occurred. Please try again later."),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    details = None
    if isinstance(exc, AppError):
        code = exc.error_code
        message = str(exc.detail)
        details = exc.details
    elif isinstance(exc, exceptions.ValidationError):
        code = "VALIDATION_ERROR"
        details = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        non_field = details.get("non_field_errors") if isinstance(details, dict) else None
        message = str(non_field[0]) if non_field else _DEFAULT_MESSAGES["VALIDATION_ERROR"]
    else:
        raw_code = getattr(exc, "default_code", "error")
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            raw_code = str(exc.detail["code"])
        code = _CODE_OVERRIDES.get(raw_code, str(raw_code).upper())
        message = _message_from_detail(exc.detail) or "Request failed."

    response.data = error_payload(code, message, details)
    return response
