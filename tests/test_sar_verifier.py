from unittest.mock import MagicMock, Mock

import pytest
import requests
from django.test import override_settings

from greenwash_detector.sar_verifier import SarVerifier


@pytest.fixture
def measurements():
    return {
        "backscatter": {
            "before_vv_db": -10.0, "after_vv_db": -12.0,
            "before_vh_db": -16.0, "after_vh_db": -17.0,
            "before_vh_vv_ratio": 0.25, "after_vh_vv_ratio": 0.3,
            "vv_change_db": -2.0, "vh_change_db": -1.0,
        },
        "areas": {"flooded_area_m2": 200.0, "observed_area_m2": 950.0},
        "buffer_area_m2": 1000.0, "water_mask_year": 2017,
    }


@pytest.fixture
def verifier(measurements):
    ee = MagicMock()
    evaluate = Mock(side_effect=[{
        "before_orbits": {"42": 3}, "after_orbits": {"42": 4}, "water_count": 1,
    }, measurements])
    return SarVerifier(ee_module=ee, evaluator=evaluate)


def run(verifier, category="solar", **kwargs):
    arguments = {
        "lat": 9.5, "lon": 76.4,
        "before_start": "2018-07-01", "before_end": "2018-08-01",
        "after_start": "2018-08-01", "after_end": "2018-09-01",
        "claimed_category": category,
    }
    arguments.update(kwargs)
    return verifier.verify(**arguments)


def test_measured_area_fraction_and_linear_ratio_are_returned(verifier):
    result = run(verifier)

    assert result["status"] == "verified"
    assert result["flooded_fraction"] == pytest.approx(0.2)
    assert result["observed_fraction"] == pytest.approx(0.95)
    assert result["sar_change_db"] == -2.0
    assert result["after_vh_vv_ratio"] == 0.3
    assert result["water_mask_year"] == 2017
    assert result["relative_orbit"] == 42
    assert "does not prove" in result["reason"]
    verifier._ee.Geometry.Point.assert_called_once_with([76.4, 9.5])
    verifier._ee.Geometry.Point.return_value.buffer.assert_called_once_with(2000)


def test_empty_collection_is_unverifiable(verifier):
    verifier._evaluator.side_effect = [{"before_orbits": {}, "after_orbits": {}, "water_count": 1}]

    result = run(verifier)

    assert result["status"] == "unverifiable"
    assert "Insufficient" in result["reason"]
    assert result["flooded_fraction"] is None
    assert verifier._evaluator.call_count == 1


def test_different_orbits_are_not_compared(verifier):
    verifier._evaluator.side_effect = [{
        "before_orbits": {"42": 3}, "after_orbits": {"43": 3}, "water_count": 1,
    }]
    assert run(verifier)["status"] == "unverifiable"


def test_gee_decimal_orbit_keys_match_integer_formatted_keys(verifier, measurements):
    verifier._evaluator.side_effect = [{
        "before_orbits": {"165.0": 6}, "after_orbits": {"165": 8}, "water_count": 1,
    }, measurements]
    result = run(verifier)
    assert result["status"] == "verified"
    assert result["relative_orbit"] == 165
    assert result["before_scene_count"] == 6
    assert result["after_scene_count"] == 8


def test_fractional_orbit_numbers_are_not_truncated_into_matches(verifier):
    verifier._evaluator.side_effect = [{
        "before_orbits": {"42.5": 3}, "after_orbits": {"42.5": 3}, "water_count": 1,
    }]
    assert run(verifier)["status"] == "unverifiable"


def test_missing_pre_event_water_mask_is_unverifiable(verifier):
    verifier._evaluator.side_effect = [{
        "before_orbits": {"42": 3}, "after_orbits": {"42": 3}, "water_count": 0,
    }]
    result = run(verifier)
    assert result["status"] == "unverifiable"
    assert "pre-event" in result["reason"]


@pytest.mark.parametrize("error", [TimeoutError, requests.Timeout])
def test_timeout_retries_once_then_returns_unverifiable(verifier, error):
    verifier._evaluator.side_effect = error("private remote details")

    result = run(verifier)

    assert result["status"] == "unverifiable"
    assert "one retry" in result["reason"]
    assert "private" not in result["reason"]
    assert verifier._evaluator.call_count == 2


def test_transient_timeout_can_recover(verifier, measurements):
    verifier._evaluator.side_effect = [
        TimeoutError(),
        {"before_orbits": {"42": 2}, "after_orbits": {"42": 2}, "water_count": 1},
        measurements,
    ]
    assert run(verifier)["status"] == "verified"
    assert verifier._evaluator.call_count == 3


def test_non_timeout_error_is_not_retried(verifier):
    verifier._evaluator.side_effect = RuntimeError("private credentials")
    result = run(verifier)
    assert result["status"] == "unverifiable"
    assert "private" not in result["reason"]
    assert verifier._evaluator.call_count == 1


def test_insufficient_coverage_is_not_reported_as_dry(verifier, measurements):
    measurements["areas"]["observed_area_m2"] = 300.0
    result = run(verifier)
    assert result["status"] == "unverifiable"
    assert result["observed_fraction"] == 0.3
    assert result["flooded_fraction"] is None


def test_null_pixels_are_unverifiable(verifier, measurements):
    measurements["backscatter"]["after_vv_db"] = None
    assert run(verifier)["status"] == "unverifiable"


@pytest.mark.parametrize("category", ["solar", "wind", "reforestation"])
def test_category_screen_is_explicitly_heuristic(verifier, category):
    result = run(verifier, category)
    assert result["status"] == "verified"
    assert "heuristic" in result["reason"]
    assert "does not prove" in result["reason"]


def test_water_category_can_conflict(verifier):
    result = run(verifier, "water")
    assert result["status"] == "inconsistent"
    assert "not proof of greenwashing" in result["reason"]


def test_thresholds_can_be_changed_without_editing_verifier(verifier):
    with override_settings(SAR_CATEGORY_THRESHOLDS={"solar": {"vv_db": (-11.0, None)}}):
        result = run(verifier)
    assert result["status"] == "inconsistent"
    assert result["thresholds"]["category"] == {"vv_db": (-11.0, None)}


def test_unknown_category_preserves_measurements_but_not_a_verdict(verifier):
    result = run(verifier, "transport")
    assert result["status"] == "unverifiable"
    assert result["flooded_fraction"] == 0.2


@pytest.mark.parametrize("arguments", [
    {"lat": 91}, {"lon": float("nan")}, {"before_start": "not-a-date"},
    {"before_end": "2018-08-15"},
])
def test_invalid_input_does_not_call_gee(verifier, arguments):
    assert run(verifier, **arguments)["status"] == "unverifiable"
    verifier._evaluator.assert_not_called()


def test_flood_image_uses_negative_change_and_permanent_water_mask(verifier):
    before, after, water, region = [MagicMock() for _index in range(4)]

    verifier._measure(before, after, water, region)

    after.select.return_value.subtract.return_value.lt.assert_called_with(-3.0)
    after.select.return_value.lt.assert_called_with(-15.0)
    water.eq.assert_called_once_with(3)
    water.eq.return_value.unmask.assert_called_once_with(0)
    water.neq.assert_not_called()
    verifier._ee.Image.pixelArea.assert_called_once()
    verifier._ee.Reducer.sum.assert_called_once()
    region.area.assert_called_once_with(1)


def test_rest_request_has_bounded_timeout(verifier, measurements):
    response = Mock(status_code=200)
    response.json.return_value = {"result": measurements}
    verifier._session = Mock()
    verifier._session.post.return_value = response

    assert verifier._request_value(Mock()) == measurements

    arguments = verifier._session.post.call_args.kwargs
    assert arguments["timeout"] == 45
    assert arguments["max_allowed_time"] == 45
    response.close.assert_called_once()


@pytest.mark.parametrize("status, error", [
    (504, {}),
    (400, {"status": "DEADLINE_EXCEEDED"}),
    (400, {"message": "Computation timed out."}),
])
def test_server_timeout_is_retried_exactly_once(verifier, status, error):
    verifier._evaluator = None
    response = Mock(status_code=status)
    response.json.return_value = {"error": error}
    verifier._session = Mock()
    verifier._session.post.return_value = response

    result = run(verifier)

    assert result["status"] == "unverifiable"
    assert "one retry" in result["reason"]
    assert verifier._session.post.call_count == 2
    assert response.close.call_count == 2


def test_context_manager_closes_session(verifier):
    session = Mock()
    verifier._session = session
    with verifier:
        pass
    session.close.assert_called_once()


def test_failed_initialization_is_noninteractive_and_safe(monkeypatch):
    verifier = SarVerifier()
    initialize = Mock(side_effect=RuntimeError("private service-account contents"))
    monkeypatch.setattr(verifier, "_initialize", initialize)

    result = run(verifier)

    assert result["status"] == "unverifiable"
    assert "initialization failed" in result["reason"]
    assert "private" not in result["reason"]
    initialize.assert_called_once()


def test_invalid_reduction_scale_does_not_request_data(verifier):
    with override_settings(SAR_REDUCTION_SCALE_METRES=0):
        assert run(verifier)["status"] == "unverifiable"
    verifier._evaluator.assert_not_called()


def test_collection_filters_and_water_mask_precede_the_event(verifier):
    run(verifier)

    ee = verifier._ee
    ee.ImageCollection.assert_any_call("COPERNICUS/S1_GRD")
    ee.ImageCollection.assert_any_call("JRC/GSW1_4/YearlyHistory")
    ee.Filter.eq.assert_any_call("instrumentMode", "IW")
    ee.Filter.eq.assert_any_call("orbitProperties_pass", "DESCENDING")
    ee.Filter.eq.assert_any_call("relativeOrbitNumber_start", 42)
    ee.Filter.listContains.assert_any_call("transmitterReceiverPolarisation", "VV")
    ee.Filter.listContains.assert_any_call("transmitterReceiverPolarisation", "VH")
    ee.ImageCollection.return_value.filterDate.assert_any_call("1984-01-01", "2018-01-01")


def test_zero_detected_flood_area_is_distinct_from_missing_data(verifier, measurements):
    measurements["areas"]["flooded_area_m2"] = 0.0
    result = run(verifier)
    assert result["status"] == "verified"
    assert result["flooded_fraction"] == 0.0


def test_sparse_jrc_water_domain_does_not_discard_valid_sar_land(verifier, measurements):
    measurements["areas"]["water_map_area_m2"] = 20.0
    result = run(verifier)
    assert result["status"] == "verified"
    assert result["observed_fraction"] == 0.95
    assert result["water_map_coverage_fraction"] == 0.02
    assert result["flooded_fraction"] == 0.2


def test_invalid_area_measurements_are_not_clipped_into_valid_results(verifier, measurements):
    measurements["areas"]["flooded_area_m2"] = 1000.0
    result = run(verifier)
    assert result["status"] == "unverifiable"
    assert result["flooded_fraction"] is None


def test_initialization_uses_existing_credentials_without_interactive_auth(monkeypatch):
    import ee

    monkeypatch.delenv("EARTHENGINE_TOKEN", raising=False)
    credentials = Mock()
    monkeypatch.setattr(ee.data, "get_persistent_credentials", Mock(return_value=credentials))
    initialize = Mock()
    authenticate = Mock()
    session_factory = Mock()
    monkeypatch.setattr(ee, "Initialize", initialize)
    monkeypatch.setattr(ee, "Authenticate", authenticate)
    monkeypatch.setattr("google.auth.transport.requests.AuthorizedSession", session_factory)

    with override_settings(EE_SERVICE_ACCOUNT="", EE_PRIVATE_KEY_FILE=""):
        verifier = SarVerifier()
        verifier._initialize()
        verifier.close()

    assert initialize.call_args.kwargs["credentials"] is credentials
    assert initialize.call_args.kwargs["http_transport"].timeout == 45
    session_factory.assert_called_once_with(
        credentials, max_refresh_attempts=0, refresh_timeout=45,
    )
    authenticate.assert_not_called()