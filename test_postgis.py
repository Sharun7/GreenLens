#!/usr/bin/env python
"""
test_postgis.py — Verify PostGIS connection and GeoDjango setup.

Usage (from project root with venv activated):
    python test_postgis.py
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenlens.settings")

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from django.db import connection


def check_postgis():
    print("=" * 60)
    print("GreenLens — PostGIS Connection Test")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Basic connectivity
        cursor.execute("SELECT version();")
        pg_version = cursor.fetchone()[0]
        print(f"\n✔  PostgreSQL: {pg_version[:60]}...")

        # PostGIS availability
        cursor.execute("SELECT PostGIS_Full_Version();")
        postgis_version = cursor.fetchone()[0]
        print(f"✔  PostGIS: {postgis_version[:80]}...")

        # Spatial query smoke-test
        cursor.execute(
            "SELECT ST_AsText(ST_MakePoint(28.9784, 41.0082));"
        )
        point = cursor.fetchone()[0]
        print(f"✔  Spatial query (Istanbul): {point}")

        # Extensions present
        cursor.execute(
            "SELECT extname FROM pg_extension WHERE extname LIKE 'postgis%';"
        )
        exts = [row[0] for row in cursor.fetchall()]
        print(f"✔  Extensions installed: {', '.join(exts)}")

    print("\n✅  All checks passed — GeoDjango is ready.\n")


if __name__ == "__main__":
    try:
        check_postgis()
    except Exception as exc:
        print(f"\n❌  Connection failed: {exc}")
        sys.exit(1)
