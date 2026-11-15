from unittest.mock import Mock

import pytest
import requests

from data_ingestion.earthdata_auth import (
    EarthdataAuthenticationError,
    EarthdataRequestError,
    earthdata_get,
)
from data_ingestion.nasa_fetcher import NASAClimateDataFetcher


URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
TEST_TOKEN = "test-only-not-a-real-token"


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("EARTHDATA_TOKEN", TEST_TOKEN)
    response = Mock(status_code=200)
    response.json.return_value = {"feed": {"entry": [{"id": "sample-granule"}]}}
    request = Mock(return_value=response)
    monkeypatch.setattr("data_ingestion.earthdata_auth.requests.get", request)
    return request


def test_bearer_header_timeout_and_no_redirects(transport):
    params = {"page_size": 1}
    response = earthdata_get(URL, params=params, timeout=20)

    assert response is transport.return_value
    transport.assert_called_once_with(
        URL, params=params,
        headers={
            "Authorization": f"Bearer {TEST_TOKEN}",
            "User-Agent": "GreenLens/1.0 (climate-risk-research)",
        },
        timeout=20, allow_redirects=False,
    )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_token_fails_before_request(monkeypatch, transport, value):
    if value is None:
        monkeypatch.delenv("EARTHDATA_TOKEN")
    else:
        monkeypatch.setenv("EARTHDATA_TOKEN", value)

    with pytest.raises(EarthdataAuthenticationError, match="not configured"):
        earthdata_get(URL)
    transport.assert_not_called()


@pytest.mark.parametrize("status, message", [(401, "expired"), (403, "permissions")])
def test_auth_failures_are_safe(transport, caplog, status, message):
    transport.return_value.status_code = status
    transport.return_value.text = TEST_TOKEN

    with pytest.raises(EarthdataAuthenticationError, match=message) as caught:
        earthdata_get(URL)

    assert TEST_TOKEN not in str(caught.value)
    assert TEST_TOKEN not in caplog.text
    transport.return_value.close.assert_called_once()


@pytest.mark.parametrize("error_type", [requests.Timeout, requests.ConnectionError])
def test_transport_failure_does_not_expose_exception_contents(transport, error_type):
    transport.side_effect = error_type(f"Sensitive request: {TEST_TOKEN}")

    with pytest.raises(EarthdataRequestError, match="could not be reached") as caught:
        earthdata_get(URL)

    assert TEST_TOKEN not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("url", [
    "http://cmr.earthdata.nasa.gov/search/granules.json",
    "https://example.com/",
    "https://earthdata.nasa.gov.example.com/",
    "https://username:password@cmr.earthdata.nasa.gov/",
])
def test_credentials_are_not_sent_to_untrusted_urls(transport, url):
    with pytest.raises(EarthdataRequestError, match="HTTPS Earthdata or ASF"):
        earthdata_get(url)
    transport.assert_not_called()


def test_redirect_is_not_followed(transport):
    transport.return_value.status_code = 302

    with pytest.raises(EarthdataRequestError, match="redirect"):
        earthdata_get(URL)

    assert transport.call_count == 1
    assert transport.call_args.kwargs["allow_redirects"] is False


def test_http_error_hides_response_and_exception_details(transport):
    transport.return_value.status_code = 503
    transport.return_value.raise_for_status.side_effect = requests.HTTPError(TEST_TOKEN)

    with pytest.raises(EarthdataRequestError, match="HTTP 503") as caught:
        earthdata_get(URL)
    assert TEST_TOKEN not in str(caught.value)


def test_rotated_token_is_read_from_environment_each_time(monkeypatch, transport):
    earthdata_get(URL)
    monkeypatch.setenv("EARTHDATA_TOKEN", "rotated-test-only-token")
    earthdata_get(URL)

    assert transport.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer rotated-test-only-token"
    )


def test_nasa_fetcher_uses_earthdata_token_without_legacy_session(transport):
    fetcher = NASAClimateDataFetcher.__new__(NASAClimateDataFetcher)
    fetcher._throttle = Mock()
    fetcher._session = Mock()

    assert fetcher._cmr_granule_search("collection", "75,8,77,10") == [
        {"id": "sample-granule"},
    ]
    fetcher._session.get.assert_not_called()
    transport.assert_called_once()


def test_nasa_fetcher_returns_empty_results_on_auth_failure(transport, monkeypatch):
    transport.return_value.status_code = 401
    warning = Mock()
    monkeypatch.setattr("data_ingestion.nasa_fetcher.logger.warning", warning)
    fetcher = NASAClimateDataFetcher.__new__(NASAClimateDataFetcher)
    fetcher._throttle = Mock()
    fetcher._session = Mock()

    assert fetcher._cmr_granule_search("collection", "75,8,77,10") == []
    warning.assert_called_once()
    assert "expired" in str(warning.call_args.args[1])
    assert TEST_TOKEN not in str(warning.call_args)
    fetcher._session.get.assert_not_called()