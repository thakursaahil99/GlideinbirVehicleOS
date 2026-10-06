"""
python manage.py run_scheduler

A tiny stand-in for Celery Beat when running without Redis/Docker. Runs the same
periodic jobs (booking reminders every 15 min, token cleanup nightly) in-process.
With Redis available, use `celery -A config beat` instead.
"""
import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.accounts.tasks import cleanup_expired_tokens
from apps.notifications.tasks import send_booking_reminder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run periodic jobs (reminders, token cleanup) without Celery Beat."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=900, help="Seconds between reminder runs (default 900).")
        parser.add_argument("--once", action="store_true", help="Run every job once and exit.")

    def handle(self, *args, interval, once, **options):
        stop = {"flag": False}
        signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
        last_cleanup_day = None
        self.stdout.write(self.style.SUCCESS(f"Scheduler running (reminders every {interval}s). Ctrl+C to stop."))
        while not stop["flag"]:
            close_old_connections()
            try:
                sent = send_booking_reminder()
                self.stdout.write(f"[{timezone.localtime():%H:%M}] reminders sent: {sent}")
                today = timezone.localdate()
                if last_cleanup_day != today and (timezone.localtime().hour >= 3 or once):
                    cleanup_expired_tokens()
                    last_cleanup_day = today
            except Exception:  # noqa: BLE001 — keep the loop alive; errors are logged
                logger.exception("Scheduled job failed")
            if once:
                break
            for _ in range(interval):
                if stop["flag"]:
                    break
                time.sleep(1)
        self.stdout.write("Scheduler stopped.")
