import io
import json
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image
from django.core.management import call_command
from django.test import override_settings

from greenwash_detector.live_connection import preview_path, read_connection_check


@pytest.fixture
def cached_check(tmp_path, monkeypatch):
    monkeypatch.setattr("greenwash_detector.live_connection.CACHE_DIR", tmp_path)
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(image, format="PNG")
    response = Mock()
    response.iter_content.return_value = [image.getvalue()]
    manager = MagicMock()
    manager.__enter__.return_value = response
    monkeypatch.setattr("greenwash_detector.management.commands.verify_gee_connection.requests.get", Mock(return_value=manager))
    optical = MagicMock()
    optical._ee.Number.return_value.add.return_value.getInfo.return_value = 2
    optical.get_ndvi_change.return_value = {"source": "gee", "before_ndvi": 0.4, "after_ndvi": 0.5}
    optical.generate_thumbnail_urls.return_value = {
        "source": "gee", "before_url": "https://example.com/before?fixture-marker",
        "after_url": "https://example.com/after?fixture-marker",
    }
    monkeypatch.setattr("greenwash_detector.management.commands.verify_gee_connection.SatelliteVerifier", Mock(return_value=optical))
    sar = MagicMock()
    sar.__enter__.return_value.verify.return_value = {
        "status": "inconsistent", "sar_change_db": 0.5, "flooded_fraction": 0.01,
        "observed_fraction": 1, "reason": "Heuristic test only",
    }
    monkeypatch.setattr("greenwash_detector.management.commands.verify_gee_connection.SarVerifier", Mock(return_value=sar))
    with override_settings(EE_PROJECT_ID="test-gee-project"):
        call_command("verify_gee_connection", before_year=2024, after_year=2025)
        yield tmp_path


def test_cached_receipt_contains_no_signed_urls_or_credentials(cached_check):
    raw = (cached_check / "latest.json").read_text()
    assert "fixture-marker" not in raw
    assert "before_url" not in raw
    assert read_connection_check()["project"] == "test-gee-project"
    assert preview_path("before").is_file()
    assert preview_path("credentials") is None


def test_reference_page_and_previews_only_read_cached_files(client, cached_check):
    response = client.get("/resources/", HTTP_HOST="localhost")
    assert response.status_code == 200
    assert b"Reference-location functional check" in response.content
    response = client.get("/resources/gee-preview/before/", HTTP_HOST="localhost")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert client.get("/resources/gee-preview/credentials/", HTTP_HOST="localhost").status_code == 404


def test_project_mismatch_cannot_reuse_another_projects_check(cached_check):
    with override_settings(EE_PROJECT_ID="different-project"):
        assert read_connection_check() is None


def test_corrupt_receipt_is_unavailable_not_a_page_error(cached_check):
    (cached_check / "latest.json").write_text(json.dumps({"project": "test-gee-project", "check_id": "../../.env"}))
    assert read_connection_check() is None