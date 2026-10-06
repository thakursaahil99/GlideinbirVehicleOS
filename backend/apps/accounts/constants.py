from django.db import models


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    AGENCY_ADMIN = "AGENCY_ADMIN", "Agency Admin"
    AGENCY_MANAGER = "AGENCY_MANAGER", "Agency Manager"
    AGENCY_STAFF = "AGENCY_STAFF", "Agency Staff"
    CUSTOMER = "CUSTOMER", "Customer"


AGENCY_ROLES = frozenset({Role.AGENCY_ADMIN, Role.AGENCY_MANAGER, Role.AGENCY_STAFF})


class StaffPermission(models.TextChoices):
    BOOKING_VIEW = "BOOKING_VIEW", "View bookings"
    BOOKING_CREATE = "BOOKING_CREATE", "Create bookings"
    BOOKING_UPDATE = "BOOKING_UPDATE", "Update bookings"
    BOOKING_CANCEL = "BOOKING_CANCEL", "Cancel bookings"
    CUSTOMER_VIEW = "CUSTOMER_VIEW", "View customers"
    CUSTOMER_CREATE = "CUSTOMER_CREATE", "Create customers"
    CUSTOMER_UPDATE = "CUSTOMER_UPDATE", "Update customers"
    VEHICLE_VIEW = "VEHICLE_VIEW", "View vehicles"
    VEHICLE_CREATE = "VEHICLE_CREATE", "Create vehicles"
    JOB_CARD_VIEW = "JOB_CARD_VIEW", "View job cards"
    JOB_CARD_UPDATE = "JOB_CARD_UPDATE", "Update job cards"
    PAYMENT_VIEW = "PAYMENT_VIEW", "View payments"
    INVOICE_VIEW = "INVOICE_VIEW", "View invoices"
    REPORT_VIEW = "REPORT_VIEW", "View reports"
    SERVICE_MANAGE = "SERVICE_MANAGE", "Manage services"


# Sensible defaults applied when a manager / staff member is created.
DEFAULT_MANAGER_PERMISSIONS = [
    StaffPermission.BOOKING_VIEW, StaffPermission.BOOKING_CREATE, StaffPermission.BOOKING_UPDATE,
    StaffPermission.BOOKING_CANCEL, StaffPermission.CUSTOMER_VIEW, StaffPermission.CUSTOMER_CREATE,
    StaffPermission.CUSTOMER_UPDATE, StaffPermission.VEHICLE_VIEW, StaffPermission.VEHICLE_CREATE,
    StaffPermission.JOB_CARD_VIEW, StaffPermission.JOB_CARD_UPDATE,
]
DEFAULT_STAFF_PERMISSIONS = [
    StaffPermission.BOOKING_VIEW, StaffPermission.CUSTOMER_VIEW, StaffPermission.VEHICLE_VIEW,
    StaffPermission.JOB_CARD_VIEW, StaffPermission.JOB_CARD_UPDATE,
]
