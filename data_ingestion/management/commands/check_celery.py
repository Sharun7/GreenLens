"""
data_ingestion/management/commands/check_celery.py

Django management command to verify Celery + Redis are reachable and to
display the configured beat schedule and startup instructions.

Usage:
    python manage.py check_celery
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check Redis/Celery connectivity and show the beat schedule."

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.MIGRATE_HEADING("  GreenLens — Celery / Redis Health Check"))
        self.stdout.write("=" * 60 + "\n")

        # ── 1. Redis connectivity ──────────────────────────────────────
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.stdout.write(f"Broker URL : {broker_url}")
        self._check_redis(broker_url)

        # ── 2. Celery worker inspection ───────────────────────────────
        self.stdout.write("\n── Active workers ──────────────────────────────────────")
        self._inspect_workers()

        # ── 3. Beat schedule ──────────────────────────────────────────
        self.stdout.write("\n── Configured beat schedule ────────────────────────────")
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
        if not schedule:
            self.stdout.write(self.style.WARNING("  No CELERY_BEAT_SCHEDULE defined in settings."))
        else:
            for name, entry in schedule.items():
                self.stdout.write(
                    f"  {self.style.SUCCESS(name)}\n"
                    f"    task     : {entry['task']}\n"
                    f"    schedule : {entry['schedule']}\n"
                )

        # ── 4. Startup instructions ───────────────────────────────────
        self.stdout.write("\n── How to start Celery ──────────────────────────────────")
        self.stdout.write(
            self.style.HTTP_INFO(
                "  # In a separate terminal — start the worker:\n"
                "  celery -A greenlens worker -l info --concurrency=4\n\n"
                "  # In another terminal — start the beat scheduler:\n"
                "  celery -A greenlens beat -l info "
                "--scheduler django_celery_beat.schedulers:DatabaseScheduler\n\n"
                "  # Or run both in one process (development only):\n"
                "  celery -A greenlens worker -l info -B "
                "--scheduler django_celery_beat.schedulers:DatabaseScheduler\n"
            )
        )
        self.stdout.write("=" * 60 + "\n")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _check_redis(self, broker_url: str) -> None:
        try:
            import redis as redis_lib

            # Parse redis://host:port/db
            url = broker_url.replace("redis://", "")
            host_port, _, db = url.partition("/")
            host, _, port = host_port.partition(":")
            r = redis_lib.Redis(
                host=host or "localhost",
                port=int(port or 6379),
                db=int(db or 0),
                socket_connect_timeout=3,
            )
            pong = r.ping()
            if pong:
                self.stdout.write(self.style.SUCCESS("Redis     : ✓ reachable (PONG)"))
            else:
                self.stdout.write(self.style.WARNING("Redis     : no PONG response"))
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"Redis     : ✗ unreachable — {exc}\n"
                                 "           Start Redis with:  docker run -p 6379:6379 redis:7-alpine")
            )

    def _inspect_workers(self) -> None:
        try:
            from greenlens.celery import app

            inspector = app.control.inspect(timeout=3)
            active = inspector.active()
            if active is None:
                self.stdout.write(
                    self.style.WARNING(
                        "  No workers responding.  Start one with:\n"
                        "    celery -A greenlens worker -l info"
                    )
                )
                return
            for worker_name, tasks in active.items():
                self.stdout.write(
                    self.style.SUCCESS(f"  Worker: {worker_name}") +
                    f" — {len(tasks)} active task(s)"
                )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Worker inspection failed: {exc}"))
