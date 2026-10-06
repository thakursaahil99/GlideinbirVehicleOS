import threading
from datetime import time, timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.audit_logs.models import AuditAction, AuditLog
from apps.availability.services import AvailabilityService
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services import BookingService
from apps.core.exceptions import BusinessRuleViolation
from apps.customers.models import AgencyCustomer
from apps.notifications.models import Channel, Notification
from apps.organizations.models import Membership, OrganizationStatus
from apps.vendors.models import Holiday, ResourceType, ServiceResource, SpecialWorkingDay
from apps.vendors.services import get_agency_settings

from .conftest import at, next_weekday

pytestmark = pytest.mark.django_db

SLOTS = "/api/v1/availability/slots/"
BOOKINGS = "/api/v1/bookings/"


def hhmm(slots, only_available=True):
    return [timezone.localtime(s.start).strftime("%H:%M") for s in slots if s.available or not only_available]


def book(client, shop, vehicle, start, **extra):
    return client.post(BOOKINGS, {"vendor_service": str(shop.offering.id), "vehicle": str(vehicle.id),
                                  "start_datetime": start.isoformat(), **extra})


class TestAvailabilityEngine:
    def test_spec_example_two_hour_service(self, shop):
        """09:00–13:00 / 14:00–19:00 with a 2 h service → 09, 11, 14, 16."""
        day = next_weekday(0)
        assert hhmm(AvailabilityService(shop.offering).get_slots(day)) == ["09:00", "11:00", "14:00", "16:00"]

    def test_buffer_changes_step(self, shop):
        settings_obj = get_agency_settings(shop.org)
        settings_obj.buffer_minutes = 30
        settings_obj.save()
        day = next_weekday(0)
        # 09:00 + 2h + 30m → 11:30 (ends 13:30 > 13:00, dropped); 14:00, 16:30 (ends 18:30)
        assert hhmm(AvailabilityService(shop.offering).get_slots(day)) == ["09:00", "14:00", "16:30"]

    def test_custom_slot_interval(self, shop):
        settings_obj = get_agency_settings(shop.org)
        settings_obj.slot_interval_minutes = 60
        settings_obj.save()
        day = next_weekday(0)
        assert hhmm(AvailabilityService(shop.offering).get_slots(day)) == [
            "09:00", "10:00", "11:00", "14:00", "15:00", "16:00", "17:00"]

    def test_closed_on_sunday_holiday_and_special_day(self, shop):
        sunday = next_weekday(6)
        assert AvailabilityService(shop.offering).get_slots(sunday) == []
        monday = next_weekday(0)
        Holiday.objects.create(organization=shop.org, name="Festival", start_date=monday, end_date=monday)
        assert AvailabilityService(shop.offering).get_slots(monday) == []
        SpecialWorkingDay.objects.create(organization=shop.org, date=sunday, opens_at=time(10), closes_at=time(14))
        assert hhmm(AvailabilityService(shop.offering).get_slots(sunday)) == ["10:00", "12:00"]

    def test_window_and_past(self, shop):
        svc = AvailabilityService(shop.offering)
        with pytest.raises(BusinessRuleViolation):
            svc.validate_day(timezone.localdate() - timedelta(days=1))
        with pytest.raises(BusinessRuleViolation):
            svc.validate_day(timezone.localdate() + timedelta(days=31))

    def test_lead_time_hides_too_soon_slots(self, shop):
        day = next_weekday(0)
        fake_now = at(day, "08:30")
        assert hhmm(AvailabilityService(shop.offering, now=fake_now).get_slots(day))[0] == "11:00"  # 09:00 < now+60m
        assert hhmm(AvailabilityService(shop.offering, now=fake_now, enforce_lead_time=False).get_slots(day))[0] \
            == "09:00"

    def test_capacity_counts_existing_bookings(self, shop, booker, make_offering):
        day = next_weekday(0)
        c = booker()
        BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                              start_datetime=at(day, "09:00"))
        slots = AvailabilityService(shop.offering).get_slots(day)
        first = slots[0]
        assert not first.available and first.reason == "FULL"

    def test_resources_limit_parallel_bookings(self, shop, booker):
        shop.offering.capacity = 5
        shop.offering.required_resource_type = ResourceType.BAY
        shop.offering.save()
        ServiceResource.objects.create(organization=shop.org, name="Bay 1", resource_type=ResourceType.BAY)
        day = next_weekday(0)
        c1, c2 = booker(), booker()
        b1 = BookingService.create(actor=c1.user, vehicle_id=c1.vehicle.id, vendor_service_id=shop.offering.id,
                                   start_datetime=at(day, "09:00"))
        assert b1.assigned_resource.name == "Bay 1"
        slot = AvailabilityService(shop.offering).get_slots(day)[0]
        assert not slot.available and slot.reason == "NO_RESOURCE"
        with pytest.raises(BusinessRuleViolation) as exc:
            BookingService.create(actor=c2.user, vehicle_id=c2.vehicle.id, vendor_service_id=shop.offering.id,
                                  start_datetime=at(day, "09:00"))
        assert exc.value.error_code == "BOOKING_SLOT_UNAVAILABLE"

    def test_slots_api(self, auth_client, shop, customer):
        day = next_weekday(0)
        res = auth_client(customer).get(f"{SLOTS}?vendor_service={shop.offering.id}&date={day}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["timezone"] == "Asia/Kolkata" and data["duration_minutes"] == 120
        assert [s["start"][11:16] for s in data["slots"]] == ["09:00", "11:00", "14:00", "16:00"]
        days = auth_client(customer).get(f"/api/v1/availability/days/?vendor_service={shop.offering.id}&days=7")
        assert days.status_code == 200 and len(days.json()["data"]["days"]) == 7

    def test_slots_hidden_for_inactive_vendor_or_service(self, auth_client, shop, customer):
        day = next_weekday(0)
        shop.org.status = OrganizationStatus.SUSPENDED
        shop.org.save()
        assert auth_client(customer).get(f"{SLOTS}?vendor_service={shop.offering.id}&date={day}").status_code == 404


class TestBookingCreation:
    def test_customer_books_a_slot(self, auth_client, shop, booker, django_capture_on_commit_callbacks):
        c = booker()
        day = next_weekday(0)
        with django_capture_on_commit_callbacks(execute=True):
            res = book(auth_client(c.user), shop, c.vehicle, at(day, "11:00"), customer_notes="Strange noise")
        assert res.status_code == 201, res.json()
        data = res.json()["data"]
        assert data["booking_number"].startswith(f"BK-{timezone.localdate().year}-")
        assert data["status"] == "PENDING" and data["quoted_price"] == "3499.00"
        assert data["end_datetime"][11:16] == "13:00"
        assert "internal_notes" not in data  # hidden from customers
        assert AgencyCustomer.objects.filter(organization=shop.org, customer=c.profile).exists()
        assert AuditLog.objects.filter(action=AuditAction.BOOKING_CREATED).exists()
        assert Notification.objects.filter(recipient=c.user, channel=Channel.IN_APP, event="BOOKING_CREATED").exists()
        assert Notification.objects.filter(recipient=shop.admin, event="NEW_BOOKING_FOR_AGENCY").exists()
        assert Notification.objects.filter(channel=Channel.EMAIL, status="SENT").exists()  # delivered via Celery

    def test_booking_numbers_are_sequential(self, shop, booker):
        day = next_weekday(0)
        numbers = []
        for t in ("09:00", "11:00"):
            c = booker()
            numbers.append(BookingService.create(actor=c.user, vehicle_id=c.vehicle.id,
                                                 vendor_service_id=shop.offering.id,
                                                 start_datetime=at(day, t)).booking_number)
        assert int(numbers[1][-6:]) == int(numbers[0][-6:]) + 1

    def test_auto_confirm(self, shop, booker):
        s = get_agency_settings(shop.org)
        s.auto_confirm_bookings = True
        s.save()
        c = booker()
        b = BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                  start_datetime=at(next_weekday(0), "09:00"))
        assert b.status == BookingStatus.CONFIRMED and b.confirmed_at

    @pytest.mark.parametrize("start,code", [("10:00", "BOOKING_SLOT_UNAVAILABLE"),  # not a generated slot
                                            ("12:00", "BOOKING_SLOT_UNAVAILABLE")])
    def test_off_grid_time_rejected(self, auth_client, shop, booker, start, code):
        c = booker()
        res = book(auth_client(c.user), shop, c.vehicle, at(next_weekday(0), start))
        assert res.status_code == 409 and res.json()["error"]["code"] == code

    def test_cannot_book_someone_elses_vehicle(self, auth_client, shop, booker):
        mine, theirs = booker(), booker()
        res = book(auth_client(mine.user), shop, theirs.vehicle, at(next_weekday(0), "09:00"))
        assert res.status_code == 404 and res.json()["error"]["code"] == "VEHICLE_NOT_FOUND"

    def test_vehicle_type_must_be_supported(self, auth_client, shop, make_customer, make_vehicle):
        profile = make_customer()
        bike = make_vehicle(profile, vehicle_type="BIKE")
        res = book(auth_client(profile.user), shop, bike, at(next_weekday(0), "09:00"))
        assert res.status_code == 400 and res.json()["error"]["code"] == "VEHICLE_TYPE_NOT_SUPPORTED"

    def test_suspended_vendor_cannot_receive_bookings(self, auth_client, shop, booker):
        shop.org.status = OrganizationStatus.SUSPENDED
        shop.org.save()
        c = booker()
        res = book(auth_client(c.user), shop, c.vehicle, at(next_weekday(0), "09:00"))
        assert res.status_code == 400 and res.json()["error"]["code"] == "SERVICE_NOT_BOOKABLE"

    def test_inactive_service_cannot_be_booked(self, auth_client, shop, booker):
        shop.offering.active = False
        shop.offering.save()
        c = booker()
        assert book(auth_client(c.user), shop, c.vehicle, at(next_weekday(0), "09:00")).status_code == 400

    def test_same_vehicle_cannot_double_book(self, shop, booker, make_offering):
        other = make_offering(shop, "car-wash")
        c = booker()
        day = next_weekday(0)
        BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                              start_datetime=at(day, "09:00"))
        with pytest.raises(BusinessRuleViolation) as exc:
            BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=other.id,
                                  start_datetime=at(day, "09:45"))
        assert exc.value.error_code == "VEHICLE_ALREADY_BOOKED"

    def test_pickup_requires_address(self, auth_client, shop, booker):
        c = booker()
        res = book(auth_client(c.user), shop, c.vehicle, at(next_weekday(0), "09:00"), pickup_requested=True)
        assert res.json()["error"]["code"] == "PICKUP_ADDRESS_REQUIRED"

    def test_naive_datetime_rejected(self, shop, booker):
        from datetime import datetime

        c = booker()
        with pytest.raises(BusinessRuleViolation):
            BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                  start_datetime=datetime.combine(next_weekday(0), time(9)))

    def test_agency_books_for_linked_customer_only(self, auth_client, shop, agency_b, booker):
        c = booker()
        client = auth_client(shop.admin)
        res = book(client, shop, c.vehicle, at(next_weekday(0), "09:00"), customer=str(c.profile.id))
        assert res.status_code == 404  # not linked yet → invisible
        AgencyCustomer.objects.create(organization=shop.org, customer=c.profile)
        res = book(client, shop, c.vehicle, at(next_weekday(0), "09:00"), customer=str(c.profile.id))
        assert res.status_code == 201 and res.json()["data"]["source"] == "AGENCY"


@pytest.mark.skipif(connection.vendor == "sqlite" and "memory" in str(connection.settings_dict["TEST"].get("NAME") or "memory"),
                    reason="threads need a file-backed database")
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
class TestConcurrentBooking:
    def test_two_customers_race_for_the_same_slot(self, shop, booker):
        """Mandatory: simultaneous requests for one slot → only the available capacity succeeds."""
        racers = [booker() for _ in range(5)]
        start = at(next_weekday(0), "09:00")
        barrier = threading.Barrier(len(racers))
        results = []

        def attempt(c):
            try:
                barrier.wait()
                BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                      start_datetime=start)
                results.append("ok")
            except BusinessRuleViolation as exc:
                results.append(exc.error_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(c,)) for c in racers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("ok") == 1, results
        assert results.count("BOOKING_SLOT_UNAVAILABLE") == 4
        assert Booking.objects.filter(start_datetime=start).count() == 1

    def test_capacity_two_allows_exactly_two(self, shop, booker):
        shop.offering.capacity = 2
        shop.offering.save()
        racers = [booker() for _ in range(6)]
        start = at(next_weekday(0), "14:00")
        barrier = threading.Barrier(len(racers))
        results = []

        def attempt(c):
            try:
                barrier.wait()
                BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                      start_datetime=start)
                results.append("ok")
            except BusinessRuleViolation as exc:
                results.append(exc.error_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(c,)) for c in racers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("ok") == 2, results


class TestBookingIsolationAndVisibility:
    def _booking(self, shop, booker, t="09:00"):
        c = booker()
        return c, BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                        start_datetime=at(next_weekday(0), t))

    def test_agency_a_requests_agency_b_booking(self, auth_client, shop, agency_b, booker):
        _, booking = self._booking(shop, booker)
        client = auth_client(agency_b.admin)
        assert client.get(f"{BOOKINGS}{booking.id}/").status_code in (403, 404)
        assert client.post(f"{BOOKINGS}{booking.id}/confirm/").status_code in (403, 404)
        assert client.post(f"{BOOKINGS}{booking.id}/cancel/", {"reason": "x"}).status_code in (403, 404)
        assert client.get(BOOKINGS).json()["data"] == []

    def test_customer_sees_only_own_bookings(self, auth_client, shop, booker):
        c1, b1 = self._booking(shop, booker, "09:00")
        c2, b2 = self._booking(shop, booker, "11:00")
        ids = [b["id"] for b in auth_client(c1.user).get(BOOKINGS).json()["data"]]
        assert ids == [str(b1.id)]
        assert auth_client(c1.user).get(f"{BOOKINGS}{b2.id}/").status_code == 404

    def test_staff_see_only_assigned_bookings(self, auth_client, shop, booker):
        _, b1 = self._booking(shop, booker, "09:00")
        _, b2 = self._booking(shop, booker, "11:00")
        BookingService.assign(booking=b1, actor=shop.admin, staff_id=shop.staff.id)
        ids = [b["id"] for b in auth_client(shop.staff).get(BOOKINGS).json()["data"]]
        assert ids == [str(b1.id)]
        assert len(auth_client(shop.admin).get(BOOKINGS).json()["data"]) == 2

    def test_staff_without_booking_view_denied(self, auth_client, shop):
        Membership.objects.filter(user=shop.staff).update(permissions=[])
        assert auth_client(shop.staff).get(BOOKINGS).status_code == 403

    def test_calendar_feed(self, auth_client, shop, booker):
        _, booking = self._booking(shop, booker)
        day = next_weekday(0)
        res = auth_client(shop.admin).get(f"{BOOKINGS}calendar/", {"start": at(day, "00:00").isoformat(),
                                                                    "end": at(day, "23:59").isoformat()})
        assert res.status_code == 200
        event = res.json()["data"][0]
        assert event["id"] == str(booking.id) and event["color"] and event["extended"]["booking_number"]


class TestLifecycle:
    def _booking(self, shop, booker, t="09:00"):
        c = booker()
        return c, BookingService.create(actor=c.user, vehicle_id=c.vehicle.id, vendor_service_id=shop.offering.id,
                                        start_datetime=at(next_weekday(0), t))

    def test_confirm_assign_and_invalid_transition(self, auth_client, shop, booker):
        _, b = self._booking(shop, booker)
        client = auth_client(shop.admin)
        assert client.post(f"{BOOKINGS}{b.id}/confirm/").json()["data"]["status"] == "CONFIRMED"
        res = client.post(f"{BOOKINGS}{b.id}/assign/", {"staff": str(shop.staff.id)})
        assert res.status_code == 200 and res.json()["data"]["status"] == "ASSIGNED"
        res = client.post(f"{BOOKINGS}{b.id}/complete/")
        assert res.status_code == 409 and res.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
        history = client.get(f"{BOOKINGS}{b.id}/history/").json()["data"]["status"]
        assert [h["to_status"] for h in history] == ["PENDING", "CONFIRMED", "ASSIGNED"]

    def test_staff_double_assignment_conflict(self, shop, booker):
        _, b1 = self._booking(shop, booker, "09:00")
        shop.offering.capacity = 2
        shop.offering.save()
        _, b2 = self._booking(shop, booker, "09:00")
        BookingService.assign(booking=b1, actor=shop.admin, staff_id=shop.staff.id)
        with pytest.raises(BusinessRuleViolation) as exc:
            BookingService.assign(booking=b2, actor=shop.admin, staff_id=shop.staff.id)
        assert exc.value.error_code == "STAFF_CONFLICT"

    def test_customer_cancels_and_history_is_kept(self, auth_client, shop, booker):
        c, b = self._booking(shop, booker)
        res = auth_client(c.user).post(f"{BOOKINGS}{b.id}/cancel/", {"reason": "Plans changed"})
        assert res.status_code == 200
        b.refresh_from_db()
        assert b.status == "CANCELLED" and b.cancelled_by == c.user and b.cancellation_reason == "Plans changed"
        assert Booking.objects.filter(pk=b.pk).exists()  # never deleted
        # Slot is free again.
        assert AvailabilityService(shop.offering).get_slots(next_weekday(0))[0].available
        assert Notification.objects.filter(recipient=shop.admin, event="BOOKING_CANCELLED").exists()

    def test_cancel_requires_reason_and_respects_cutoff(self, auth_client, shop, booker):
        c, b = self._booking(shop, booker)
        assert auth_client(c.user).post(f"{BOOKINGS}{b.id}/cancel/", {"reason": ""}).status_code == 400
        Booking.objects.filter(pk=b.pk).update(start_datetime=timezone.now() + timedelta(minutes=30),
                                               end_datetime=timezone.now() + timedelta(minutes=150))
        res = auth_client(c.user).post(f"{BOOKINGS}{b.id}/cancel/", {"reason": "late"})
        assert res.json()["error"]["code"] == "CUTOFF_PASSED"
        # The agency can still cancel.
        assert auth_client(shop.admin).post(f"{BOOKINGS}{b.id}/cancel/", {"reason": "Customer called"}).status_code \
            == 200

    def test_staff_cannot_cancel_without_permission(self, auth_client, shop, booker):
        _, b = self._booking(shop, booker)
        BookingService.assign(booking=b, actor=shop.admin, staff_id=shop.staff.id)
        assert auth_client(shop.staff).post(f"{BOOKINGS}{b.id}/cancel/", {"reason": "x"}).status_code == 403

    def test_reschedule_revalidates_and_records_history(self, auth_client, shop, booker):
        c, b = self._booking(shop, booker, "09:00")
        _, other = self._booking(shop, booker, "14:00")
        client = auth_client(c.user)
        day = next_weekday(0)
        taken = client.post(f"{BOOKINGS}{b.id}/reschedule/", {"start_datetime": at(day, "14:00").isoformat()})
        assert taken.status_code == 409
        res = client.post(f"{BOOKINGS}{b.id}/reschedule/", {"start_datetime": at(day, "16:00").isoformat(),
                                                             "reason": "Office meeting"})
        assert res.status_code == 200, res.json()
        assert res.json()["data"]["start_datetime"][11:16] == "16:00"
        history = client.get(f"{BOOKINGS}{b.id}/history/").json()["data"]["reschedules"]
        assert history[0]["old_start"][11:16] == "09:00" and history[0]["reason"] == "Office meeting"
        # Old slot freed, new one taken.
        slots = {timezone.localtime(s.start).strftime("%H:%M"): s.available
                 for s in AvailabilityService(shop.offering).get_slots(day)}
        assert slots["09:00"] and not slots["16:00"]

    def test_reschedule_into_own_slot_is_allowed(self, shop, booker):
        c, b = self._booking(shop, booker, "09:00")
        moved = BookingService.reschedule(booking=b, actor=c.user, start_datetime=at(next_weekday(0), "09:00"))
        assert moved.start_datetime == at(next_weekday(0), "09:00")

    def test_internal_notes_controlled_editing(self, auth_client, shop, booker):
        c, b = self._booking(shop, booker)
        assert auth_client(c.user).patch(f"{BOOKINGS}{b.id}/", {"internal_notes": "x"}).status_code == 403
        res = auth_client(shop.admin).patch(f"{BOOKINGS}{b.id}/", {"internal_notes": "VIP"})
        assert res.status_code == 200 and res.json()["data"]["internal_notes"] == "VIP"
        assert auth_client(c.user).patch(f"{BOOKINGS}{b.id}/", {"customer_notes": "Please wash too"}).status_code \
            == 200

    def test_allowed_actions(self, auth_client, shop, booker):
        c, b = self._booking(shop, booker)
        assert set(auth_client(c.user).get(f"{BOOKINGS}{b.id}/").json()["data"]["allowed_actions"]) == {
            "cancel", "reschedule"}
        admin_actions = auth_client(shop.admin).get(f"{BOOKINGS}{b.id}/").json()["data"]["allowed_actions"]
        assert {"confirm", "reject", "cancel", "reschedule", "assign"} <= set(admin_actions)

    def test_reminder_task_sends_once(self, shop, booker):
        from apps.notifications.tasks import send_booking_reminder

        _, b = self._booking(shop, booker)
        Booking.objects.filter(pk=b.pk).update(start_datetime=timezone.now() + timedelta(hours=3),
                                               end_datetime=timezone.now() + timedelta(hours=5))
        assert send_booking_reminder() == 1
        assert send_booking_reminder() == 0
        assert Notification.objects.filter(event="BOOKING_REMINDER", channel=Channel.IN_APP).count() == 1
