"""Read-only access to locally cached, explicitly labelled GEE reference checks."""

import json
import uuid
from pathlib import Path

from django.conf import settings


CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "gee_connection"


def read_connection_check():
    try:
        receipt = json.loads((CACHE_DIR / "latest.json").read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or receipt.get("project") != settings.EE_PROJECT_ID:
            return None
        check_id = receipt.get("check_id", "")
        if uuid.UUID(check_id).hex != check_id:
            return None
        if not all((CACHE_DIR / f"{check_id}-{period}.png").is_file() for period in ("before", "after")):
            return None
        return receipt
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def preview_path(period):
    if period not in ("before", "after"):
        return None
    receipt = read_connection_check()
    return CACHE_DIR / f"{receipt['check_id']}-{period}.png" if receipt else None