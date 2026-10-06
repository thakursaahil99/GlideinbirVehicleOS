import itertools
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.constants import DEFAULT_STAFF_PERMISSIONS, Role
from apps.accounts.models import User
from apps.organizations.models import Membership, Organization, OrganizationStatus

PASSWORD = "Str0ng!Passw0rd"
_seq = itertools.count(1)


@pytest.fixture(autouse=True)
def _isolation(settings, tmp_path):
    from django.core.cache import cache

    settings.MEDIA_ROOT = tmp_path / "media"
    cache.clear()  # throttle history lives in the cache
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(role=Role.CUSTOMER, email=None, password=PASSWORD, **extra):
        n = next(_seq)
        return User.objects.create_user(
            email=email or f"user{n}@example.com", password=password,
            full_name=extra.pop("full_name", f"User {n}"), role=role, **extra,
        )

    return _make


@pytest.fixture
def make_agency(db, make_user):
    def _make(name=None, status=OrganizationStatus.ACTIVE):
        n = next(_seq)
        org = Organization.objects.create(
            name=name or f"Agency {n}", slug=f"agency-{n}", phone="+919800000000",
            email=f"agency{n}@example.com", city="Pune", status=status,
        )
        admin = make_user(Role.AGENCY_ADMIN)
        manager = make_user(Role.AGENCY_MANAGER)
        staff = make_user(Role.AGENCY_STAFF)
        Membership.objects.create(user=admin, organization=org)
        Membership.objects.create(user=manager, organization=org, permissions=[])
        Membership.objects.create(user=staff, organization=org,
                                  permissions=[str(p) for p in DEFAULT_STAFF_PERMISSIONS])
        return SimpleNamespace(org=org, admin=admin, manager=manager, staff=staff)

    return _make


@pytest.fixture
def auth_client():
    """APIClient authenticated with a real JWT access token (exercises the auth stack)."""

    def _client(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    return _client


@pytest.fixture
def super_admin(make_user):
    return make_user(Role.SUPER_ADMIN)


@pytest.fixture
def customer(make_user):
    from apps.customers.services import CustomerService

    user = make_user(Role.CUSTOMER)
    CustomerService.ensure_profile(user)
    return user


@pytest.fixture
def make_customer(make_user):
    """A self-registered customer (user + profile), optionally linked to agencies."""
    from apps.customers.services import CustomerService

    def _make(*agencies, **extra):
        user = make_user(Role.CUSTOMER, **extra)
        profile = CustomerService.ensure_profile(user)
        for agency in agencies:
            CustomerService.link_to_agency(profile, getattr(agency, "org", agency))
        return profile

    return _make


@pytest.fixture
def make_vehicle():
    from apps.vehicles.models import Vehicle

    counter = itertools.count(1000)

    def _make(customer, **extra):
        defaults = {"vehicle_type": "CAR", "brand": "Maruti", "model": "Swift",
                    "registration_number": f"MH12AB{next(counter)}"}
        defaults.update(extra)
        return Vehicle.objects.create(customer=customer, **defaults)

    return _make


@pytest.fixture
def agency_a(make_agency):
    return make_agency("Agency A")


@pytest.fixture
def agency_b(make_agency):
    return make_agency("Agency B")


@pytest.fixture
def make_offering():
    """An agency's VendorService for a seeded catalog service."""
    from apps.services.models import Service, VendorService

    def _make(agency, slug="general-service", **extra):
        org = getattr(agency, "org", agency)
        return VendorService.objects.create(organization=org, service=Service.objects.get(slug=slug), **extra)

    return _make


def next_weekday(weekday=0, min_days_ahead=2):
    """A date at least ``min_days_ahead`` days out that falls on ``weekday`` (0=Mon)."""
    from datetime import timedelta

    from django.utils import timezone

    day = timezone.localdate() + timedelta(days=min_days_ahead)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def at(day, hhmm):
    """Aware datetime at the agency's local time (Asia/Kolkata)."""
    import zoneinfo
    from datetime import datetime, time

    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))


@pytest.fixture
def shop(agency_a, make_offering):
    """Agency A open Mon–Sat 09–13 / 14–19 with a 120-minute, capacity-1 general service."""
    from datetime import time

    from apps.vendors.models import WorkingHours

    WorkingHours.objects.bulk_create(
        [WorkingHours(organization=agency_a.org, weekday=d, opens_at=time(9), closes_at=time(13)) for d in range(6)]
        + [WorkingHours(organization=agency_a.org, weekday=d, opens_at=time(14), closes_at=time(19)) for d in range(6)]
    )
    agency_a.offering = make_offering(agency_a, "general-service", custom_duration=120, capacity=1,
                                      pickup_available=True)
    return agency_a


@pytest.fixture
def booker(make_customer, make_vehicle):
    """A customer user with a car, ready to book."""
    from types import SimpleNamespace

    def _make():
        profile = make_customer()
        return SimpleNamespace(user=profile.user, profile=profile, vehicle=make_vehicle(profile))

    return _make
