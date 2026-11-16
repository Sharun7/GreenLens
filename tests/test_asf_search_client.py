from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.cache import cache

from data_ingestion.asf_search_client import search_sar_metadata


@pytest.fixture(autouse=True)
def clear_metadata_cache(monkeypatch):
    cache.clear()
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    yield
    cache.clear()


def test_empty_catalog_is_not_a_failed_search(monkeypatch):
    search = Mock(return_value=[])
    monkeypatch.setattr("data_ingestion.asf_search_client.asf.search", search)
    result = search_sar_metadata(9.5, 76.4, "2018-07-01", "2018-09-01")
    assert result["granules"] == []
    assert result["datasets"][0]["status"] == "empty"
    assert "No NISAR coverage yet" in result["datasets"][0]["reason"]
    assert search.call_count == 2
    assert search.call_args_list[0].kwargs["dataset"] == "NISAR-SCIENCE-PRODUCTS"


def test_metadata_is_bounded_cached_and_contains_no_raw_download(monkeypatch):
    product = SimpleNamespace(properties={
        "sceneName": "SAMPLE_SCENE", "startTime": "2026-01-01T00:00:00Z",
        "browse": ["https://datapool.asf.alaska.edu/BROWSE/example.jpg"],
        "url": "https://example.com/huge-file.zip",
    })
    search = Mock(return_value=[product])
    monkeypatch.setattr("data_ingestion.asf_search_client.asf.search", search)
    result = search_sar_metadata(9.5, 76.4, "2026-01-01", "2026-02-01", limit=3)
    assert result["granules"][0]["browse_url"].endswith("example.jpg")
    assert "url" not in result["granules"][0]
    assert search.call_args.kwargs["maxResults"] == 3
    assert search.call_args.kwargs["intersectsWith"] == "POINT(76.4 9.5)"
    assert search_sar_metadata(9.5, 76.4, "2026-01-01", "2026-02-01", limit=3)["cached"]
    assert search.call_count == 2


def test_failures_do_not_claim_no_coverage_or_expose_credentials(monkeypatch):
    monkeypatch.setenv("EARTHDATA_TOKEN", "test-only-private-token")
    search = Mock(side_effect=RuntimeError("test-only-private-token"))
    monkeypatch.setattr("data_ingestion.asf_search_client.asf.search", search)
    result = search_sar_metadata(9.5, 76.4, "2026-01-01", "2026-02-01")
    assert all(item["status"] == "unavailable" for item in result["datasets"])
    assert "test-only-private-token" not in str(result)


@pytest.mark.parametrize("lat, lon", [(float("nan"), 76), (91, 76), (9, 181)])
def test_invalid_coordinates_do_not_search(monkeypatch, lat, lon):
    search = Mock()
    monkeypatch.setattr("data_ingestion.asf_search_client.asf.search", search)
    with pytest.raises(ValueError):
        search_sar_metadata(lat, lon, "2026-01-01", "2026-02-01")
    search.assert_not_called()


def test_resources_page_does_not_search_on_initial_load(client, monkeypatch):
    search = Mock()
    monkeypatch.setattr("dashboard.resource_views.search_sar_metadata", search)
    response = client.get("/resources/", HTTP_HOST="localhost")
    assert response.status_code == 200
    assert b"Earth observation resources" in response.content
    assert b"NASA does not endorse GreenLens" in response.content
    search.assert_not_called()


def test_resources_search_and_csv_use_metadata_only(client, monkeypatch):
    search = Mock(return_value={
        "granules": [{"dataset": "Sentinel-1", "granule_id": "SCENE_1",
                      "acquired_at": "2026-01-01", "browse_url": None,
                      "catalog_url": "https://search.asf.alaska.edu/"}],
        "datasets": [], "cached": False,
    })
    monkeypatch.setattr("dashboard.resource_views.search_sar_metadata", search)
    query = {"search": "1", "latitude": "9.5", "longitude": "76.4",
             "start": "2026-01-01", "end": "2026-02-01"}
    response = client.get("/resources/", query, HTTP_HOST="localhost")
    assert response.status_code == 200
    assert b"SCENE_1" in response.content
    response = client.get("/resources/", {**query, "format": "csv"}, HTTP_HOST="localhost")
    assert response["Content-Type"].startswith("text/csv")
    assert b"SCENE_1" in response.content