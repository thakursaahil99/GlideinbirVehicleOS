from decimal import Decimal

import pytest

from apps.audit_logs.models import AuditAction, AuditLog
from apps.bookings.models import Booking
from apps.bookings.services import BookingService
from apps.inventory.models import Part, StockTransaction
from apps.invoices.models import Invoice
from apps.invoices.services import compute_line
from apps.job_cards.models import JobCard
from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.vendors.services import get_agency_settings

from .conftest import at, next_weekday

pytestmark = pytest.mark.django_db

BOOKINGS = "/api/v1/bookings/"
JOBS = "/api/v1/job-cards/"
PARTS = "/api/v1/inventory/parts/"
INVOICES = "/api/v1/invoices/"
PAYMENTS = "/api/v1/payments/"


@pytest.fixture
def received(shop, booker, auth_client):
    """A booking whose vehicle has been received (job card open)."""
    c = booker()
    booking = BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                    start_datetime=at(next_weekday(0), "09:00"))
    admin = auth_client(shop.admin)
    admin.post(f"{BOOKINGS}{booking.id}/confirm/")
    res = admin.post(f"{BOOKINGS}{booking.id}/receive-vehicle/")
    assert res.status_code == 200, res.json()
    c.booking = booking
    c.job = JobCard.objects.get(booking=booking)
    return c


@pytest.fixture
def oil(shop):
    return Part.objects.create(organization=shop.org, name="Engine oil 5W-30", sku="OIL-5W30", purchase_price=400,
                               selling_price=650, stock_quantity=10, minimum_stock=3, unit="LITRE")


class TestInventory:
    def test_crud_and_stock_is_read_only(self, auth_client, shop):
        client = auth_client(shop.admin)
        res = client.post(PARTS, {"name": "Brake pad", "sku": "bp-01", "selling_price": "1200.00",
                                  "purchase_price": "800.00", "stock_quantity": "999"})
        assert res.status_code == 201, res.json()
        assert res.json()["data"]["sku"] == "BP-01" and res.json()["data"]["stock_quantity"] == "0.00"
        assert client.post(PARTS, {"name": "Dup", "sku": "BP-01"}).status_code == 400

    def test_moves_and_ledger(self, auth_client, shop, oil):
        client = auth_client(shop.admin)
        assert client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "PURCHASE", "quantity": "5"}).status_code == 201
        assert client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "SALE", "quantity": "2"}).status_code == 201
        res = client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "SALE", "quantity": "100"})
        assert res.status_code == 400 and res.json()["error"]["code"] == "INSUFFICIENT_STOCK"
        res = client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "ADJUSTMENT", "quantity": "-1"})
        assert res.json()["error"]["code"] == "NOTE_REQUIRED"
        client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "ADJUSTMENT", "quantity": "-1", "note": "Spill"})
        oil.refresh_from_db()
        assert oil.stock_quantity == Decimal("12")
        ledger = client.get(f"{PARTS}{oil.id}/transactions/").json()["data"]
        assert [t["transaction_type"] for t in ledger] == ["ADJUSTMENT", "SALE", "PURCHASE"]
        assert ledger[0]["balance_after"] == "12.00"
        assert AuditLog.objects.filter(action=AuditAction.INVENTORY_ADJUSTED).exists()

    def test_low_stock_filter_and_permissions(self, auth_client, shop, oil):
        Part.objects.create(organization=shop.org, name="Wiper", sku="W1", stock_quantity=1, minimum_stock=2)
        rows = auth_client(shop.staff).get(f"{PARTS}?low_stock=true").json()["data"]
        assert [r["sku"] for r in rows] == ["W1"]
        assert auth_client(shop.staff).post(f"{PARTS}{oil.id}/move/", {"transaction_type": "SALE",
                                                                       "quantity": "1"}).status_code == 403

    def test_inventory_tenant_isolation(self, auth_client, shop, agency_b, oil):
        client = auth_client(agency_b.admin)
        assert client.get(f"{PARTS}{oil.id}/").status_code == 404
        assert client.post(f"{PARTS}{oil.id}/move/", {"transaction_type": "SALE", "quantity": "1"}).status_code == 404

    def test_db_constraint_blocks_negative_stock(self, oil):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            Part.objects.filter(pk=oil.pk).update(stock_quantity=-1)


class TestJobCardFlow:
    def test_full_workshop_to_payment_flow(self, auth_client, shop, received, oil, django_capture_on_commit_callbacks):
        admin, customer = auth_client(shop.admin), auth_client(received.user)
        job = received.job
        assert job.job_card_number.startswith("JOB-")

        # Inspection + details
        res = admin.put(f"{JOBS}{job.id}/inspection/", {"items": [
            {"area": "TYRES", "result": "ATTENTION", "notes": "Front left worn"},
            {"area": "BRAKES", "result": "OK"}]}, format="json")
        assert res.status_code == 200 and res.json()["data"]["status"] == "INSPECTION"
        assert admin.patch(f"{JOBS}{job.id}/", {"odometer": 45000, "fuel_level": "HALF"}).status_code == 200
        received.vehicle.refresh_from_db()
        assert received.vehicle.odometer == 45000

        # Start work → booking in progress
        assert admin.post(f"{JOBS}{job.id}/start-work/").json()["data"]["status"] == "WORK_IN_PROGRESS"
        assert Booking.objects.get(pk=received.booking.pk).status == "IN_PROGRESS"

        # Parts consume stock
        res = admin.post(f"{JOBS}{job.id}/parts/", {"part": str(oil.id), "quantity": "4"})
        assert res.status_code == 201, res.json()
        oil.refresh_from_db()
        assert oil.stock_quantity == Decimal("6")
        assert StockTransaction.objects.get(job_card=job, transaction_type="USED_IN_JOB").quantity == Decimal("-4")
        res = admin.post(f"{JOBS}{job.id}/parts/", {"part": str(oil.id), "quantity": "50"})
        assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK"
        usage_id = admin.get(f"{JOBS}{job.id}/").json()["data"]["parts_used"][0]["id"]
        assert admin.post(f"{JOBS}{job.id}/parts/{usage_id}/return/", {"quantity": "1"}).status_code == 200
        oil.refresh_from_db()
        assert oil.stock_quantity == Decimal("7")

        # Additional work needs customer approval
        res = admin.post(f"{JOBS}{job.id}/additional-work/", {"description": "Replace front-left tyre",
                                                              "estimated_cost": "3000.00"})
        assert res.status_code == 201 and res.json()["data"]["status"] == "PENDING"
        work_id = res.json()["data"]["id"]
        assert Booking.objects.get(pk=received.booking.pk).status == "WAITING_FOR_APPROVAL"
        assert Notification.objects.filter(recipient=received.user, event="ADDITIONAL_WORK_REQUESTED").exists()
        res = admin.post(f"{JOBS}{job.id}/complete/")
        assert res.json()["error"]["code"] == "APPROVAL_PENDING"
        # Customer approves from their account
        res = customer.post(f"{JOBS}{job.id}/additional-work/{work_id}/respond/", {"approve": True,
                                                                                    "response": "Go ahead"})
        assert res.status_code == 200 and res.json()["data"]["status"] == "APPROVED"
        assert Booking.objects.get(pk=received.booking.pk).status == "IN_PROGRESS"

        # Complete → booking completed → invoice generated
        with django_capture_on_commit_callbacks(execute=True):
            res = admin.post(f"{JOBS}{job.id}/complete/", {"technician_notes": "All good"})
        assert res.status_code == 200 and res.json()["data"]["status"] == "COMPLETED"
        booking = Booking.objects.get(pk=received.booking.pk)
        assert booking.status == "COMPLETED"
        invoice = Invoice.objects.get(booking=booking)
        lines = list(invoice.items.order_by("created_at").values_list("item_type", "quantity", "unit_price"))
        assert lines == [("SERVICE", Decimal("1.00"), Decimal("3499.00")),
                         ("ADDITIONAL_WORK", Decimal("1.00"), Decimal("3000.00")),
                         ("PART", Decimal("3.00"), Decimal("650.00"))]
        expected = sum(compute_line(q, p, 18)[2] for _, q, p in lines)
        assert invoice.total == expected == Decimal("9969.82")
        assert invoice.pdf.name.endswith(".pdf")
        assert Notification.objects.filter(recipient=received.user, event="INVOICE_GENERATED").exists()

        # Customer sees and pays the invoice via the mock gateway
        inv = customer.get(f"{INVOICES}{invoice.id}/").json()["data"]
        assert inv["balance_due"] == "9969.82" and inv["has_pdf"]
        pdf = customer.get(f"{INVOICES}{invoice.id}/pdf/")
        assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
        assert b"".join(pdf.streaming_content).startswith(b"%PDF")
        failed = customer.post(f"{PAYMENTS}pay/", {"invoice": str(invoice.id), "method": "UPI", "simulate": "fail"})
        assert failed.json()["data"]["status"] == "FAILED"
        with django_capture_on_commit_callbacks(execute=True):
            ok = customer.post(f"{PAYMENTS}pay/", {"invoice": str(invoice.id), "method": "UPI",
                                                   "idempotency_key": "key-123"})
        assert ok.status_code == 201 and ok.json()["data"]["status"] == "SUCCEEDED"
        retry = customer.post(f"{PAYMENTS}pay/", {"invoice": str(invoice.id), "method": "UPI",
                                                  "idempotency_key": "key-123"})
        assert retry.json()["data"]["id"] == ok.json()["data"]["id"]  # no double charge
        invoice.refresh_from_db()
        assert invoice.payment_status == "PAID" and invoice.amount_paid == Decimal("9969.82")
        assert Booking.objects.get(pk=booking.pk).payment_status == "PAID"
        assert Notification.objects.filter(recipient=received.user, event="PAYMENT_RECEIVED").exists()

        # Partial refund by agency admin only
        pid = ok.json()["data"]["id"]
        assert auth_client(shop.manager).post(f"{PAYMENTS}{pid}/refund/", {"amount": "100", "reason": "x"}) \
            .status_code == 403
        res = admin.post(f"{PAYMENTS}{pid}/refund/", {"amount": "969.82", "reason": "Goodwill"})
        assert res.status_code == 200 and res.json()["data"]["status"] == "PARTIALLY_REFUNDED"
        invoice.refresh_from_db()
        assert invoice.payment_status == "PARTIALLY_PAID" and invoice.amount_paid == Decimal("9000.00")
        assert AuditLog.objects.filter(action=AuditAction.PAYMENT_REFUNDED).exists()

        # Job card locks after completion; close it.
        assert admin.patch(f"{JOBS}{job.id}/", {"technician_notes": "edit"}).json()["error"]["code"] == "JOB_CARD_LOCKED"
        assert admin.post(f"{JOBS}{job.id}/close/").json()["data"]["status"] == "CLOSED"

    def test_auto_approval_when_configured(self, auth_client, shop, received):
        s = get_agency_settings(shop.org)
        s.additional_work_requires_approval = False
        s.save()
        admin = auth_client(shop.admin)
        admin.post(f"{JOBS}{received.job.id}/start-work/")
        res = admin.post(f"{JOBS}{received.job.id}/additional-work/", {"description": "Wiper", "estimated_cost": "300"})
        assert res.json()["data"]["status"] == "APPROVED" and res.json()["data"]["auto_approved"]
        assert Booking.objects.get(pk=received.booking.pk).status == "IN_PROGRESS"

    def test_customer_cannot_edit_or_respond_for_others(self, auth_client, shop, received, booker):
        admin = auth_client(shop.admin)
        admin.post(f"{JOBS}{received.job.id}/start-work/")
        work_id = admin.post(f"{JOBS}{received.job.id}/additional-work/", {"description": "X",
                                                                           "estimated_cost": "10"}).json()["data"]["id"]
        stranger = booker()
        assert auth_client(stranger.user).post(f"{JOBS}{received.job.id}/additional-work/{work_id}/respond/",
                                               {"approve": True}).status_code == 404
        owner = auth_client(received.user)
        assert owner.patch(f"{JOBS}{received.job.id}/", {"technician_notes": "hack"}).status_code == 404
        assert owner.get(f"{JOBS}{received.job.id}/").status_code == 200

    def test_job_cards_tenant_isolation(self, auth_client, received, agency_b):
        client = auth_client(agency_b.admin)
        assert client.get(f"{JOBS}{received.job.id}/").status_code == 404
        assert client.post(f"{JOBS}{received.job.id}/start-work/").status_code == 404

    def test_staff_job_card_permissions(self, auth_client, shop, received):
        # Staff not assigned to the booking can't see the job card at all.
        assert auth_client(shop.staff).get(f"{JOBS}{received.job.id}/").status_code == 404
        BookingService.assign(booking=received.booking, actor=shop.admin, staff_id=shop.staff.id)
        assert auth_client(shop.staff).post(f"{JOBS}{received.job.id}/start-work/").status_code == 200


class TestPayments:
    def test_prepayment_required_flow(self, auth_client, shop, booker, django_capture_on_commit_callbacks):
        s = get_agency_settings(shop.org)
        s.require_online_payment = True
        s.save()
        c = booker()
        booking = BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                        start_datetime=at(next_weekday(0), "09:00"))
        pending = Payment.objects.get(booking=booking)
        assert pending.status == "PENDING" and pending.amount == Decimal("4128.82")  # 3499 + 18%
        res = auth_client(c.user).post(f"{PAYMENTS}pay/", {"payment": str(pending.id), "method": "CARD"})
        assert res.status_code == 201
        booking.refresh_from_db()
        assert booking.payment_status == "PAID"
        # Later the invoice picks up the prepayment.
        Booking.objects.filter(pk=booking.pk).update(status="COMPLETED")
        from apps.invoices.services import InvoiceService

        invoice = InvoiceService.generate_for_booking(booking)
        assert invoice.payment_status == "PAID" and invoice.balance_due == 0

    def test_offline_payment_and_validation(self, auth_client, shop, received):
        Booking.objects.filter(pk=received.booking.pk).update(status="COMPLETED")
        from apps.invoices.services import InvoiceService

        invoice = InvoiceService.generate_for_booking(received.booking)
        admin = auth_client(shop.admin)
        res = admin.post(f"{PAYMENTS}record/", {"invoice": str(invoice.id), "amount": "999999", "method": "CASH"})
        assert res.json()["error"]["code"] == "INVALID_AMOUNT"
        res = admin.post(f"{PAYMENTS}record/", {"invoice": str(invoice.id), "amount": "1000", "method": "CASH",
                                                "reference": "RCPT-1"})
        assert res.status_code == 201
        invoice.refresh_from_db()
        assert invoice.payment_status == "PARTIALLY_PAID"
        # Discount can't change once money was received.
        res = admin.patch(f"{INVOICES}{invoice.id}/", {"discount": "100"})
        assert res.json()["error"]["code"] == "INVOICE_HAS_PAYMENTS"

    def test_invoice_discount_and_void(self, auth_client, shop, received):
        Booking.objects.filter(pk=received.booking.pk).update(status="COMPLETED")
        from apps.invoices.services import InvoiceService

        invoice = InvoiceService.generate_for_booking(received.booking)
        assert InvoiceService.generate_for_booking(received.booking).pk == invoice.pk  # idempotent
        admin = auth_client(shop.admin)
        res = admin.patch(f"{INVOICES}{invoice.id}/", {"discount": "499"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["subtotal"] == "3499.00" and data["discount"] == "499.00"
        assert data["tax"] == "540.00" and data["total"] == "3540.00"
        assert auth_client(shop.staff).patch(f"{INVOICES}{invoice.id}/", {"discount": "1"}).status_code == 403
        res = admin.post(f"{INVOICES}{invoice.id}/void/", {"reason": "Duplicate"})
        assert res.json()["data"]["status"] == "VOID"
        assert AuditLog.objects.filter(action=AuditAction.INVOICE_VOIDED).exists()

    def test_finance_isolation(self, auth_client, shop, received, agency_b, booker):
        Booking.objects.filter(pk=received.booking.pk).update(status="COMPLETED")
        from apps.invoices.services import InvoiceService

        invoice = InvoiceService.generate_for_booking(received.booking)
        assert auth_client(agency_b.admin).get(f"{INVOICES}{invoice.id}/").status_code == 404
        assert auth_client(agency_b.admin).post(f"{PAYMENTS}record/", {"invoice": str(invoice.id), "amount": "1",
                                                                       "method": "CASH"}).status_code == 404
        other = booker()
        assert auth_client(other.user).get(f"{INVOICES}{invoice.id}/").status_code == 404
        assert auth_client(other.user).post(f"{PAYMENTS}pay/", {"invoice": str(invoice.id),
                                                                "method": "UPI"}).status_code == 404
        assert auth_client(shop.manager).get(INVOICES).status_code == 403  # no INVOICE_VIEW code


class TestNotificationsApi:
    def test_inbox_unread_and_mark_read(self, auth_client, shop, booker):
        c = booker()
        BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                              start_datetime=at(next_weekday(0), "09:00"))
        client = auth_client(c.user)
        assert client.get("/api/v1/notifications/unread-count/").json()["data"]["unread"] == 1
        rows = client.get("/api/v1/notifications/").json()["data"]
        assert rows[0]["event"] == "BOOKING_CREATED" and not rows[0]["is_read"]
        assert client.post("/api/v1/notifications/mark-read/", {}).json()["data"]["updated"] == 1
        assert client.get("/api/v1/notifications/unread-count/").json()["data"]["unread"] == 0
        # Other users never see it.
        assert auth_client(booker().user).get("/api/v1/notifications/").json()["data"] == []

    def test_walk_in_customer_gets_sms_without_inbox(self, auth_client, shop, make_vehicle):
        res = auth_client(shop.admin).post("/api/v1/customers/", {"full_name": "Walk", "phone": "+919899999999"})
        from apps.customers.models import Customer

        walk_in = Customer.objects.get(pk=res.json()["data"]["id"])
        vehicle = make_vehicle(walk_in)
        BookingService.create(actor=shop.admin, vehicle_id=vehicle.id, vendor_service_id=shop.offering.id,
                              customer_id=walk_in.id, start_datetime=at(next_weekday(0), "09:00"))
        sms = Notification.objects.get(channel="SMS", to_address="+919899999999")
        assert sms.recipient is None and sms.status in ("PENDING", "SENT")
