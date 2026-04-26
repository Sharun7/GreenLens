"""
greenwash_detector/management/commands/batch_greenwash_check.py

Management command to run greenwash detection on all (or selected) bonds
and persist GreenwashFlag records to the database.

Usage:
    # Check all bonds (GEE + CNN — slow, ~30-60s per bond)
    python manage.py batch_greenwash_check

    # Fast mode: skip GEE, use synthetic NDVI + CNN (~100+ bonds/s)
    python manage.py batch_greenwash_check --skip-gee

    # Check only bonds without an existing flag
    python manage.py batch_greenwash_check --only-missing

    # Resume: skip bonds already checked today
    python manage.py batch_greenwash_check --resume

    # Limit to N bonds (for testing)
    python manage.py batch_greenwash_check --limit 50

    # Check specific bonds by bond_id
    python manage.py batch_greenwash_check --bond-ids AND_Sustainabili_2021 IDA_ClimateB_2020

    # Parallel fast mode (safe only with --skip-gee)
    python manage.py batch_greenwash_check --skip-gee --workers 4
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import connection

from data_ingestion.models import GreenBond
from greenwash_detector.detection_engine import GreenwashDetector
from greenwash_detector.models import GreenwashFlag


class Command(BaseCommand):
    help = "Batch-run greenwash detection for all bonds and persist GreenwashFlag records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit to first N bonds (0 = all).",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            default=False,
            help="Only process bonds that do not yet have a GreenwashFlag.",
        )
        parser.add_argument(
            "--bond-ids",
            nargs="+",
            default=[],
            metavar="BOND_ID",
            help="Process specific bond_ids only.",
        )
        parser.add_argument(
            "--skip-gee",
            action="store_true",
            default=False,
            help="Bypass Google Earth Engine; use synthetic NDVI and CNN (much faster).",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            default=False,
            help="Skip bonds that already have a GreenwashFlag checked today.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Parallel workers (safe with --skip-gee; default=1).",
        )

    def handle(self, *args, **options):
        skip_gee = options["skip_gee"]
        workers = options["workers"]

        if workers > 1 and not skip_gee:
            self.stdout.write(
                self.style.WARNING(
                    "--workers > 1 requires --skip-gee (GEE is not thread-safe). "
                    "Falling back to sequential."
                )
            )
            workers = 1

        # ── Build queryset ────────────────────────────────────────────────────
        qs = GreenBond.objects.filter(
            lat__isnull=False,
            lon__isnull=False,
        )

        if options["bond_ids"]:
            qs = qs.filter(bond_id__in=options["bond_ids"])
            self.stdout.write(
                f"Filtering to {len(options['bond_ids'])} specified bond_ids"
            )

        if options["only_missing"]:
            flagged_pks = GreenwashFlag.objects.values_list("bond_id", flat=True)
            qs = qs.exclude(pk__in=flagged_pks)
            self.stdout.write("Mode: only-missing (skipping bonds already flagged)")

        if options["resume"]:
            today = date.today()
            today_start = today.isoformat()
            today_end = (today + timedelta(days=1)).isoformat()
            already_checked = (
                GreenwashFlag.objects
                .filter(checked_at__date=today)
                .values_list("bond_id", flat=True)
            )
            qs = qs.exclude(pk__in=already_checked)
            self.stdout.write(f"Mode: resume (skipping {already_checked.count()} bonds checked today)")

        if options["limit"]:
            qs = qs[: options["limit"]]
            self.stdout.write(f"Limit: {options['limit']} bonds")

        bonds = list(qs)
        total = len(bonds)

        if total == 0:
            self.stdout.write(self.style.WARNING("No bonds to process — exiting."))
            return

        mode_label = "SYNTHETIC (fast)" if skip_gee else "GEE + CNN"
        self.stdout.write(
            self.style.HTTP_INFO(
                f"\nChecking {total} bonds for greenwashing  [mode={mode_label}, workers={workers}]\n"
            )
        )

        # ── Initialise detector once (shared across workers if sequential) ─────
        detector = GreenwashDetector(skip_gee=skip_gee)

        # ── Run checks ───────────────────────────────────────────────────────
        n_flagged = 0
        n_ok = 0
        n_errors = 0
        t_start = time.perf_counter()

        def _process_one(bond):
            """Check a single bond and persist result."""
            nonlocal n_flagged, n_ok, n_errors
            try:
                result = detector.check_bond(bond)
                flag, created = GreenwashFlag.objects.update_or_create(
                    bond=bond,
                    defaults={k: v for k, v in result.items() if k != "bond"},
                )
                if flag.is_inconsistent:
                    n_flagged += 1
                else:
                    n_ok += 1
                return flag.is_inconsistent, None
            except Exception as exc:
                n_errors += 1
                return None, (bond.bond_id, exc)

        if workers == 1:
            # Sequential run
            for i, bond in enumerate(bonds, 1):
                is_flagged, err = _process_one(bond)
                if err:
                    self.stderr.write(f"  ERROR bond {err[0]}: {err[1]}")

                if i % 100 == 0 or i == total:
                    elapsed = time.perf_counter() - t_start
                    rate = i / elapsed if elapsed > 0 else 0
                    eta_s = (total - i) / rate if rate > 0 else 0
                    self.stdout.write(
                        f"  {i:5d}/{total}  "
                        f"flagged={n_flagged}  ok={n_ok}  errors={n_errors}  "
                        f"rate={rate:.1f}/s  ETA={eta_s/60:.1f}m"
                    )
        else:
            # Parallel run (skip_gee only — each thread needs its own DB conn)
            def _thread_worker(bond):
                connection.close()
                try:
                    result = detector.check_bond(bond)
                    flag, created = GreenwashFlag.objects.update_or_create(
                        bond=bond,
                        defaults={k: v for k, v in result.items() if k != "bond"},
                    )
                    return bond.bond_id, flag.is_inconsistent, None
                except Exception as exc:
                    return bond.bond_id, None, exc

            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_thread_worker, b): b for b in bonds}
                for future in as_completed(futures):
                    bond_id, is_flagged, exc = future.result()
                    completed += 1
                    if exc:
                        n_errors += 1
                        self.stderr.write(f"  ERROR bond {bond_id}: {exc}")
                    elif is_flagged:
                        n_flagged += 1
                    else:
                        n_ok += 1

                    if completed % 100 == 0 or completed == total:
                        elapsed = time.perf_counter() - t_start
                        rate = completed / elapsed if elapsed > 0 else 0
                        eta_s = (total - completed) / rate if rate > 0 else 0
                        self.stdout.write(
                            f"  {completed:5d}/{total}  "
                            f"flagged={n_flagged}  ok={n_ok}  errors={n_errors}  "
                            f"rate={rate:.1f}/s  ETA={eta_s/60:.1f}m"
                        )

        # ── Summary ───────────────────────────────────────────────────────────
        elapsed = time.perf_counter() - t_start
        flagged_pct = (n_flagged / total * 100) if total else 0

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. {total} bonds processed in {elapsed:.1f}s"
        ))
        self.stdout.write(
            f"  Greenwash flags : {n_flagged} ({flagged_pct:.1f}%)"
        )
        self.stdout.write(f"  Consistent      : {n_ok}")
        self.stdout.write(f"  Errors          : {n_errors}")

        if n_flagged > 0:
            self.stdout.write(
                "\nTop flagged bonds (highest confidence):"
            )
            top_flags = (
                GreenwashFlag.objects
                .filter(is_inconsistent=True)
                .select_related("bond")
                .order_by("-confidence")[:10]
            )
            for flag in top_flags:
                self.stdout.write(
                    f"  {flag.bond.bond_id:<35s}  "
                    f"conf={flag.confidence:.2f}  "
                    f"ndvi={flag.ndvi_change:+.3f}  "
                    f"land={flag.satellite_land_use}"
                )
