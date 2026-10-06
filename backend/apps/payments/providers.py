"""
PaymentService → PaymentProviderInterface → concrete provider.

``MockPaymentProvider`` stands in for a real gateway (Razorpay, Stripe, …) in
development. Plug in a real one by implementing the interface and pointing
``settings.PAYMENT_PROVIDER`` at it — business logic does not change.
"""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass
class ChargeResult:
    success: bool
    transaction_id: str = ""
    failure_reason: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class RefundResult:
    success: bool
    refund_id: str = ""
    failure_reason: str = ""


class PaymentProviderInterface:
    name = "abstract"

    def charge(self, *, amount: Decimal, currency: str, method: str, reference: str, metadata: dict) -> ChargeResult:
        raise NotImplementedError

    def refund(self, *, transaction_id: str, amount: Decimal, currency: str) -> RefundResult:
        raise NotImplementedError


class MockPaymentProvider(PaymentProviderInterface):
    """Approves every charge unless ``metadata['simulate'] == 'fail'`` (handy for testing failure UX)."""

    name = "mock"

    def charge(self, *, amount, currency, method, reference, metadata):
        if metadata.get("simulate") == "fail":
            return ChargeResult(success=False, failure_reason="Card declined (simulated).")
        return ChargeResult(success=True, transaction_id=f"mock_txn_{uuid.uuid4().hex[:16]}",
                            raw={"amount": str(amount), "currency": currency, "method": method})

    def refund(self, *, transaction_id, amount, currency):
        return RefundResult(success=True, refund_id=f"mock_rfnd_{uuid.uuid4().hex[:16]}")


class OfflinePaymentProvider(PaymentProviderInterface):
    """Cash / bank transfers recorded by the agency — no gateway involved."""

    name = "offline"

    def charge(self, *, amount, currency, method, reference, metadata):
        return ChargeResult(success=True, transaction_id=f"offline_{reference or uuid.uuid4().hex[:12]}")

    def refund(self, *, transaction_id, amount, currency):
        return RefundResult(success=True, refund_id=f"offline_rfnd_{uuid.uuid4().hex[:12]}")


def get_gateway() -> PaymentProviderInterface:
    return import_string(settings.PAYMENT_PROVIDER)()


def get_offline() -> PaymentProviderInterface:
    return OfflinePaymentProvider()
