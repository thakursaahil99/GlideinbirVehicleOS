"""
Database-level double-booking guard: a resource can't hold two *active*
bookings whose time ranges overlap.

    EXCLUDE USING gist (assigned_resource_id WITH =, tstzrange(start, end) WITH &&)

Needs the ``btree_gist`` extension (bundled with standard PostgreSQL, including
the postgres:16 Docker image). If the server lacks it, the migration logs a
warning and the application-level lock + recheck remains the guard.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

ACTIVE = "('PENDING','CONFIRMED','ASSIGNED','VEHICLE_RECEIVED','IN_PROGRESS','WAITING_FOR_APPROVAL')"

ADD = f"""
ALTER TABLE bookings_booking
  ADD CONSTRAINT booking_resource_no_overlap
  EXCLUDE USING gist (
    assigned_resource_id WITH =,
    tstzrange(start_datetime, end_datetime, '[)') WITH &&
  )
  WHERE (assigned_resource_id IS NOT NULL AND status IN {ACTIVE});
"""
DROP = "ALTER TABLE bookings_booking DROP CONSTRAINT IF EXISTS booking_resource_no_overlap;"


def forwards(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'btree_gist'")
        if cur.fetchone() is None:
            logger.warning("btree_gist not available: skipping booking_resource_no_overlap constraint.")
            return
        cur.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        cur.execute(ADD)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP, params=None)


class Migration(migrations.Migration):
    dependencies = [("bookings", "0001_initial")]

    operations = [migrations.RunPython(forwards, backwards)]
