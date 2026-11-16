from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import resolve

from data_ingestion.models import ClimateHazardData, GreenBond
from data_ingestion.regulatory_compliance import RegulatoryComplianceGenerator
from greenwash_detector.detection_engine import GreenwashDetector, NDVIResult
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


class BondRouteTests(SimpleTestCase):
    def test_viewport_route_is_not_treated_as_a_bond_id(self):
        self.assertEqual(resolve("/api/bonds/viewport/").url_name, "bonds-viewport")

    def test_hazard_route_is_not_treated_as_a_bond_id(self):
        self.assertEqual(resolve("/api/bonds/hazards/").url_name, "climatehazard-list")

    def test_bond_detail_route_is_preserved(self):
        match = resolve("/api/bonds/123/")
        self.assertEqual(match.url_name, "greenbond-detail")
        self.assertEqual(match.kwargs["pk"], "123")

    @patch("greenwash_detector.satellite_verifier.SatelliteVerifier")
    def test_invalid_history_queries_do_not_start_remote_processing(self, verifier):
        client = Client(HTTP_HOST="localhost")
        invalid_values = (
            {"lat": "nan"}, {"lon": "inf"}, {"lat": "91"}, {"lon": "181"},
            {"year": "2016"}, {"year": "9999"}, {"radius_km": "-1"}, {"radius_km": "1000"},
        )
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                query = {"lat": "9.5", "lon": "76.4", "year": "2021", **invalid}
                self.assertEqual(client.get("/api/greenwash/flags/history/", query).status_code, 400)
        verifier.assert_not_called()


class SatelliteEvidenceTests(SimpleTestCase):
    def setUp(self):
        self.bond = SimpleNamespace(
            bond_id="EVIDENCE_001", lat=20.0, lon=78.0,
            issuance_date=date(2020, 1, 1), project_category="reforestation",
        )
        self.detector = GreenwashDetector.__new__(GreenwashDetector)
        self.ndvi = NDVIResult(
            pre_ndvi=0.7, post_ndvi=0.2, ndvi_change=-0.5,
            pre_date=date(2019, 1, 1), post_date=date(2021, 1, 1),
            land_use="bare_soil", source="synthetic",
            raw_metadata={"method": "synthetic"},
        )
        self.detector._get_ndvi = Mock(return_value=self.ndvi)
        self.detector._get_cnn_result = Mock(return_value=None)

    def test_synthetic_data_cannot_verify_or_flag_a_bond(self):
        result = self.detector.check_bond(self.bond)

        self.assertEqual(result["verification_status"], "unverifiable")
        self.assertFalse(result["is_inconsistent"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["ndvi_change"], 0.0)
        self.assertEqual(result["satellite_land_use"], "unknown")
        self.assertIsNone(result["pre_project_image_date"])
        self.assertIsNone(result["post_project_image_date"])
        self.assertEqual(result["raw_ee_metadata"]["source"], "synthetic")
        self.detector._get_cnn_result.assert_not_called()

    def test_satellite_evidence_can_still_flag_inconsistent_claims(self):
        self.ndvi.source = "gee"
        result = self.detector.check_bond(self.bond)

        self.assertEqual(result["verification_status"], "verifiable")
        self.assertTrue(result["is_inconsistent"])
        self.assertGreater(result["confidence"], 0.0)
        self.assertEqual(result["pre_project_image_date"], self.ndvi.pre_date)

    def test_pre_sentinel_bond_remains_unverifiable(self):
        self.bond.issuance_date = date(2010, 1, 1)
        result = self.detector.check_bond(self.bond)

        self.assertEqual(result["verification_status"], "unverifiable")
        self.detector._get_ndvi.assert_not_called()
        self.detector._get_cnn_result.assert_not_called()

    def test_classifier_can_require_real_imagery(self):
        from greenwash_detector.satellite_classifier import SatelliteClassifier

        classifier = SatelliteClassifier.__new__(SatelliteClassifier)
        classifier._skip_gee = True
        classifier._synthetic_patch_tensor = Mock()
        classifier._infer = Mock()

        with self.assertRaisesMessage(ValueError, "Satellite imagery is unavailable"):
            classifier.classify_patch(20.0, 78.0, "2020-01-01", allow_synthetic=False)

        classifier._synthetic_patch_tensor.assert_not_called()
        classifier._infer.assert_not_called()

    def test_detector_requires_real_cnn_imagery(self):
        del self.detector._get_cnn_result
        self.detector._classifier = Mock()
        self.detector._classifier.classify_patch.return_value = {
            "predicted_class": "forest", "confidence": 0.9, "all_probs": {},
        }

        result = self.detector._get_cnn_result(self.bond)

        self.assertEqual(result["predicted_class"], "forest")
        self.detector._classifier.classify_patch.assert_called_once_with(
            20.0, 78.0, "2020-01-01", allow_synthetic=False,
        )

    def test_unknown_land_cover_does_not_create_a_false_mismatch(self):
        self.ndvi.source = "gee"
        self.ndvi.land_use = "unknown"
        self.ndvi.ndvi_change = 0.1
        self.ndvi.post_ndvi = 0.6
        inconsistent, confidence = self.detector._classify(self.bond, self.ndvi)
        self.assertFalse(inconsistent)
        self.assertEqual(confidence, 0.0)


class HistoricalSatelliteEvidenceTests(SimpleTestCase):
    @patch("greenwash_detector.satellite_verifier._read_cache")
    def test_expired_thumbnail_cache_is_not_reused(self, read_cache):
        from greenwash_detector.satellite_verifier import SatelliteVerifier

        read_cache.return_value = {
            "source": "gee", "thumbnail_url": "https://example.com/expired.png",
            "generated_at": 1, "ndvi": 0.4, "n_images": 2,
        }
        result = SatelliteVerifier(skip_gee=True).get_historical_data(9.5, 76.4, 2021)
        self.assertIsNone(result["thumbnail_url"])
        self.assertEqual(result["source"], "unavailable")

    @patch("greenwash_detector.satellite_verifier._read_cache")
    def test_fresh_real_history_cache_is_preserved(self, read_cache):
        import time
        from greenwash_detector.satellite_verifier import SatelliteVerifier

        read_cache.return_value = {"source": "gee", "generated_at": time.time(), "ndvi": 0.4}
        self.assertEqual(SatelliteVerifier(skip_gee=True).get_historical_data(9.5, 76.4, 2021), read_cache.return_value)

    @patch("greenwash_detector.satellite_verifier._write_cache")
    @patch("greenwash_detector.satellite_verifier._read_cache")
    def test_legacy_synthetic_history_is_not_returned_as_satellite_evidence(self, read_cache, write_cache):
        from greenwash_detector.satellite_verifier import SatelliteVerifier

        read_cache.return_value = {
            "source": "synthetic",
            "thumbnail_url": "data:image/svg+xml;base64,ZmFrZQ==",
            "ndvi": 0.62,
            "n_images": 12,
        }
        result = SatelliteVerifier(skip_gee=True).get_historical_data(9.5, 76.4, 2021)

        self.assertEqual(result["source"], "unavailable")
        self.assertIsNone(result["thumbnail_url"])
        self.assertIsNone(result["ndvi"])
        self.assertEqual(result["n_images"], 0)
        write_cache.assert_not_called()


class OpticalThumbnailTests(SimpleTestCase):
    def test_classifier_uses_the_configured_optical_gee_initializer(self):
        from greenwash_detector.satellite_classifier import SatelliteClassifier

        classifier = SatelliteClassifier.__new__(SatelliteClassifier)
        module = object()
        with patch("greenwash_detector.satellite_verifier._init_ee", return_value=module) as initialize:
            self.assertIs(classifier._init_ee(), module)
        initialize.assert_called_once_with()

    def test_thumbnail_callable_returns_url_without_getinfo_on_a_string(self):
        from greenwash_detector.satellite_verifier import _getinfo_with_timeout

        self.assertEqual(_getinfo_with_timeout(lambda: "https://example.com/preview.png"),
                         "https://example.com/preview.png")

    def test_real_thumbnail_api_string_is_preserved(self):
        from greenwash_detector.satellite_verifier import SatelliteVerifier

        verifier = SatelliteVerifier(skip_gee=True)
        verifier._ee = MagicMock()
        collection = verifier._ee.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value.filter.return_value
        collection.size.return_value.getInfo.return_value = 2
        collection.median.return_value.clip.return_value.getThumbURL.return_value = "https://example.com/preview.png"
        result = verifier.generate_thumbnail_urls(9.5, 76.4, "2018-07-01", "2018-08-01")
        self.assertEqual(result["source"], "gee")
        self.assertEqual(result["before_url"], "https://example.com/preview.png")
        self.assertEqual(result["after_url"], "https://example.com/preview.png")

    def test_missing_land_cover_is_unknown_not_a_latitude_guess(self):
        from greenwash_detector.satellite_verifier import SatelliteVerifier

        self.assertEqual(SatelliteVerifier(skip_gee=True).classify_land_use(9.5, 76.4, "2020-01-01"), "unknown")

    def test_local_authentication_is_never_started_in_a_web_operation(self):
        import ee
        from greenwash_detector.satellite_verifier import _init_ee

        with patch.dict("os.environ", {"EARTHENGINE_TOKEN": ""}), patch.object(
            ee, "Initialize", side_effect=ee.EEException("Missing credentials"),
        ), patch.object(ee, "Authenticate") as authenticate:
            self.assertIsNone(_init_ee())
        authenticate.assert_not_called()

    def test_optical_scan_honors_configured_service_account_and_project(self):
        import ee
        from greenwash_detector.satellite_verifier import _init_ee

        with patch.dict("os.environ", {
            "EARTHENGINE_TOKEN": "", "EE_PROJECT_ID": "test-gee-project",
            "EE_SERVICE_ACCOUNT": "test-account", "EE_PRIVATE_KEY_FILE": "test-key-file",
        }), patch.object(ee, "ServiceAccountCredentials", return_value="test-credentials"), patch.object(
            ee, "Initialize",
        ) as initialize:
            self.assertIs(_init_ee(), ee)
        initialize.assert_called_once_with("test-credentials", project="test-gee-project")


class DataPipelineRealityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        cls.bond = GreenBond.objects.create(
            bond_id="PIPELINE_001",
            issuer_name="Pipeline Test Issuer",
            country="India",
            project_category="water",
            project_description="Pipeline test bond",
            bond_maturity_years=9,
            issuance_date=date(2024, 5, 1),
            currency="USD",
            amount_millions=120,
            lat=20.5937,
            lon=78.9629,
            location_confidence="country",
            data_source="CBI",
        )
        ClimateHazardData.objects.create(
            bond=cls.bond,
            flood_risk_index=0.52,
            heat_stress_index=0.46,
            drought_spei=-0.7,
            data_date=date(2026, 4, 1),
            source="nasa",
            raw_metadata={"fallback": True},
        )
        PCRScore.objects.create(
            bond=cls.bond,
            score=62.4,
            flood_contribution=12.1,
            heat_contribution=8.4,
            drought_contribution=5.0,
            model_version="v1.0.0",
            shap_values={"flood_risk_index": 12.1},
        )
        PricingGap.objects.create(
            bond=cls.bond,
            actual_spread_bps=188.0,
            predicted_spread_bps=171.0,
            data_source="synthetic",
            is_live=False,
        )
        GreenwashFlag.objects.create(
            bond=cls.bond,
            verification_status="unverifiable",
            ndvi_change=0.0,
            satellite_land_use="unknown",
            claimed_project_type="water",
            is_inconsistent=False,
            confidence=0.0,
            model_version="v1.0.0",
        )

    def test_data_pipeline_page_renders(self):
        response = self.client.get("/data-pipeline/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data Pipeline Reality")
        self.assertContains(response, "Quarterly PCRS retraining")
        self.assertContains(response, "Missing Data Handling")

    @patch("ai_features.regulatory_fetcher.fetch_and_save_regulatory_updates")
    def test_empty_regulatory_monitor_does_not_claim_coverage_or_fetch_on_request(self, fetch_updates):
        response = self.client.get("/ai/regulatory/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No regulatory records collected")
        self.assertContains(response, "does not indicate that no relevant updates")
        self.assertNotContains(response, ">Real Data<")
        fetch_updates.assert_not_called()

    def test_portfolio_page_does_not_create_a_default_portfolio(self):
        from ai_features.models import PortfolioOptimization

        response = self.client.get("/ai/portfolio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No portfolio scenario submitted")
        self.assertNotContains(response, "AI-Powered Rebalancing")
        self.assertNotContains(response, "Current Return")
        self.assertEqual(PortfolioOptimization.objects.count(), 0)

    def test_verify_idle_page_renders_coordinate_picker(self):
        response = self.client.get("/verify/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="verify-picker-map"')
        self.assertContains(response, "Pick a location on the map")

    def test_cinematic_explorer_keeps_accessible_modes_and_local_3d_assets(self):
        from django.contrib.staticfiles import finders

        response = self.client.get("/")
        for text in ('id="wb-globe-tab"', 'id="wb-map-tab"', 'id="wb-table-tab"',
                     'aria-label="Pause globe rotation"', 'aria-controls="gl-chat-panel"',
                     "css/cinematic.css", "Research, grounded in evidence."):
            self.assertContains(response, text)
        self.assertNotContains(response, "1,275+ green bonds")
        self.assertNotContains(response, "Powered by Gemini · Live bond data")
        for asset in ("js/orbital-globe.js", "js/cinematic.js", "vendor/three/three.module.min.js",
                      "vendor/three/OrbitControls.js", "vendor/three/earth-day.jpg",
                      "vendor/three/earth-normal.jpg", "vendor/three/earth-specular.jpg", "vendor/three/LICENSE"):
            self.assertIsNotNone(finders.find(asset), asset)

    def test_csv_export_respects_workbench_filters(self):
        import csv
        import io

        response = self.client.get("/export/", {"country": "India"})
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["Bond ID"] for row in rows], [self.bond.bond_id])
        response = self.client.get("/export/", {"country": "Norway"})
        self.assertEqual(len(list(csv.DictReader(io.StringIO(response.content.decode())))), 0)
        self.assertEqual(self.client.get("/export/", {"min_score": "nan"}).status_code, 400)

    def test_pricing_uses_latest_record_and_basis_point_units(self):
        PricingGap.objects.create(
            bond=self.bond, actual_spread_bps=400, predicted_spread_bps=200,
            data_source="test", is_live=False,
        )
        response = self.client.get("/pricing/")
        self.assertEqual(response.context["stats"]["total_analyzed"], 1)
        self.assertEqual(response.context["stats"]["mispriced_count"], 1)
        self.assertContains(response, "Modelled spread (bps)")
        self.assertContains(response, 'id="pricing-flagged"')
        self.assertNotContains(response, "Fitted Yield (%)")

    def test_exports_do_not_invent_isin_or_execute_spreadsheet_formulas(self):
        import csv
        import io

        self.bond.issuer_name = '=HYPERLINK("https://example.com")'
        self.bond.save()
        for path in ("/export/", "/export/sfdr/"):
            response = self.client.get(path)
            row = next(csv.DictReader(io.StringIO(response.content.decode())))
            self.assertTrue(row["Issuer Name"].startswith("'="))
            if path.endswith("sfdr/"):
                self.assertEqual(row["ISIN"], "")
                self.assertIn("not a certified", row["Report Status"])
                self.assertEqual(row["Hazard Input Status"], "Demo / fallback estimate")

    def test_profile_labels_estimated_data_and_scales_observed_confidence(self):
        flag = self.bond.greenwash_flags.first()
        flag.verification_status = "verifiable"
        flag.confidence = 0.84
        flag.raw_ee_metadata = {"source": "gee"}
        flag.before_image_url = "https://example.com/before.png"
        flag.save()
        response = self.client.get(f"/bond/{self.bond.bond_id}/")
        self.assertContains(response, "Confidence: 84%")
        self.assertContains(response, "Estimated spread")
        self.assertContains(response, "Demo / fallback estimate")
        self.assertNotContains(response, "Fairly Priced")
        flag.raw_ee_metadata = {"source": "synthetic"}
        flag.save()
        response = self.client.get(f"/bond/{self.bond.bond_id}/")
        self.assertContains(response, "Unverifiable")
        self.assertNotContains(response, 'src="https://example.com/before.png"')

    def test_about_commercial_model_shows_proposed_tiers_and_limitations(self):
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        for text in (
            'id="commercial-model"', "Commercial Model", "Asset Management Companies",
            "Regulators", "Research Institutions", "Research Tier", "Professional Tier",
            "Enterprise Tier", "€299", "€2,999", "Competitive Positioning",
            "Proposed commercial model:", "unverified planning assumptions",
            "not 1,345 independently verified projects",
        ):
            self.assertContains(response, text)

    @patch("data_ingestion.nasa_fetcher.NASAClimateDataFetcher.get_all_hazards")
    def test_verify_nearby_records_include_high_latitude_and_dateline_points(self, get_hazards):
        get_hazards.return_value = {
            "flood_risk_index": 0.4, "heat_stress_index": 0.5,
            "drought_spei": -0.6, "source": "heuristic",
        }
        high_latitude_bond = GreenBond.objects.create(
            bond_id="HIGH_LATITUDE_001", issuer_name="High Latitude Issuer",
            country="Norway", project_category="wind", project_description="Test wind project",
            bond_maturity_years=9, issuance_date=date(2024, 5, 1), currency="USD",
            amount_millions=120, lat=80.0, lon=10.0, location_confidence="country", data_source="CBI",
        )
        dateline_bond = GreenBond.objects.create(
            bond_id="DATELINE_001", issuer_name="Dateline Issuer",
            country="Fiji", project_category="water", project_description="Test water project",
            bond_maturity_years=9, issuance_date=date(2024, 5, 1), currency="USD",
            amount_millions=120, lat=0.0, lon=-179.5, location_confidence="country", data_source="CBI",
        )

        high_latitude_response = self.client.get("/verify/", {"q": "80, 0"})
        high_latitude_ids = {item["bond"].bond_id for item in high_latitude_response.context["nearby_bonds"]}
        self.assertIn(high_latitude_bond.bond_id, high_latitude_ids)

        dateline_response = self.client.get("/verify/", {"q": "0, 179.5"})
        dateline_ids = {item["bond"].bond_id for item in dateline_response.context["nearby_bonds"]}
        self.assertIn(dateline_bond.bond_id, dateline_ids)

    def test_home_map_uses_public_satellite_tiles_without_a_provider_key(self):
        from pathlib import Path
        from django.contrib.staticfiles import finders

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/workbench.js")
        controller = Path(finders.find("js/workbench.js")).read_text()
        self.assertIn("server.arcgisonline.com/ArcGIS/rest/services/World_Imagery", controller)
        self.assertIn("https://tile.openstreetmap.org/", controller)
        self.assertNotIn("mt1.google.com/vt/", controller)
        response = self.client.get(f"/bond/{self.bond.bond_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "server.arcgisonline.com/ArcGIS/rest/services/World_Imagery")
        self.assertNotContains(response, "mt1.google.com/vt/")

    @patch("geopy.geocoders.Nominatim.geocode")
    @patch("data_ingestion.nasa_fetcher.NASAClimateDataFetcher.get_all_hazards")
    def test_verify_accepts_coordinates_without_place_geocoding(self, get_hazards, geocode):
        get_hazards.return_value = {
            "flood_risk_index": 0.4, "heat_stress_index": 0.5,
            "drought_spei": -0.6, "source": "heuristic",
        }
        response = self.client.get("/verify/", {"q": "9.5, 76.4"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coordinate search")
        self.assertContains(response, "Rule-based composite")
        self.assertContains(response, "Not a PCRS model prediction")
        geocode.assert_not_called()
        get_hazards.assert_called_once_with(9.5, 76.4)

    @patch("geopy.geocoders.Nominatim.geocode")
    def test_verify_rejects_out_of_range_coordinates_without_network(self, geocode):
        for query in ("91, 181", "100, 0", "-100, 0", "+100, -181"):
            response = self.client.get("/verify/", {"q": query})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Coordinates must be within")
        geocode.assert_not_called()

    @patch("data_ingestion.nasa_fetcher.NASAClimateDataFetcher.get_all_hazards")
    @patch("geopy.geocoders.Nominatim.geocode")
    def test_verify_place_search_still_uses_nominatim(self, geocode, get_hazards):
        geocode.return_value = SimpleNamespace(latitude=9.5, longitude=76.4, address="Kochi, Kerala")
        get_hazards.return_value = {
            "flood_risk_index": 0.4, "heat_stress_index": 0.5,
            "drought_spei": -0.6, "source": "heuristic",
        }
        response = self.client.get("/verify/", {"q": "Kochi, India"})
        self.assertEqual(response.status_code, 200)
        geocode.assert_called_once()
        get_hazards.assert_called_once_with(9.5, 76.4)

    def test_esma_report_does_not_invent_compliance_evidence(self):
        report = RegulatoryComplianceGenerator.generate_esma_report(self.bond)

        for field in ("eu_taxonomy_aligned", "sfdr_classification", "external_reviewer"):
            self.assertIsNone(report[field])
        for field in ("carbon_footprint", "fossil_fuel_exposure", "biodiversity_impact"):
            self.assertIsNone(report["principal_adverse_impacts"][field])
        self.assertEqual(report["climate_risk_score"], 62.4)

    def test_data_reliability_api_still_available(self):
        response = self.client.get("/api/data-reliability/")
        self.assertEqual(response.status_code, 200)

    def test_viewport_counts_bonds_once_with_multiple_historical_scores(self):
        PCRScore.objects.create(
            bond=self.bond, score=80, flood_contribution=10,
            heat_contribution=5, drought_contribution=2,
            model_version="history-test", shap_values={},
        )
        for zoom in (2, 6):
            with self.subTest(zoom=zoom):
                response = self.client.get("/api/bonds/viewport/", {"zoom": zoom})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total_bonds"], 1)
                self.assertEqual(response.json()["clusters"][0]["count"], 1)
                self.assertEqual(response.json()["clusters"][0]["avg_pcr"], 80)

    def test_workbench_search_and_detail_preserve_demo_provenance(self):
        response = self.client.get("/api/workbench/data/", {"q": "Pipeline"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["results"][0]["satellite_status"], "Unverifiable")
        detail = self.client.get(f"/api/workbench/bonds/{self.bond.bond_id}/").json()
        self.assertEqual(detail["hazards"]["status"], "Demo / fallback estimate")
        self.assertEqual(detail["pricing_status"], "Estimated spread")
        self.assertEqual(detail["satellite"]["status"], "Unverifiable")

    def test_workbench_map_clusters_latest_scores_without_duplicate_bonds(self):
        PCRScore.objects.create(
            bond=self.bond, score=80, flood_contribution=1, heat_contribution=1,
            drought_contribution=1, model_version="new-test", shap_values={},
        )
        response = self.client.get("/api/workbench/map/", {"zoom": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["results"][0]["count"], 1)
        self.assertEqual(response.json()["results"][0]["score"], 80)

    def test_workbench_rejects_invalid_numeric_filters_and_bounds(self):
        self.assertEqual(self.client.get("/api/workbench/data/", {"min_score": "NaN"}).status_code, 400)
        self.assertEqual(self.client.get("/api/workbench/map/", {"south": 91}).status_code, 400)

    def test_workbench_review_filter_rejects_synthetic_flags(self):
        GreenwashFlag.objects.filter(bond=self.bond).update(
            verification_status="verifiable", is_inconsistent=True,
            raw_ee_metadata={"method": "synthetic"},
        )
        response = self.client.get("/api/workbench/data/", {"flagged": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)

    def test_workbench_never_labels_conflicting_synthetic_provenance_as_observed(self):
        GreenwashFlag.objects.filter(bond=self.bond).update(
            verification_status="verifiable", is_inconsistent=True,
            raw_ee_metadata={"source": "synthetic", "collection": "COPERNICUS/S2_SR_HARMONIZED"},
        )
        self.assertEqual(self.client.get("/api/workbench/data/", {"flagged": 1}).json()["total"], 0)
        self.assertEqual(self.client.get("/api/workbench/bonds/PIPELINE_001/").json()["satellite_status"], "Unverifiable")

    def test_workbench_exposes_only_manifest_backed_shap_factors(self):
        score = PCRScore.objects.get(bond=self.bond)
        score.feature_metadata = {"artifact_status": "manifest_checked"}
        score.shap_values = {"flood_risk_index": 2.5, "heat_stress_index": -4}
        score.save(update_fields=["feature_metadata", "shap_values"])
        factors = self.client.get("/api/workbench/bonds/PIPELINE_001/").json()["shap_factors"]
        self.assertEqual(factors[0]["feature"], "heat_stress_index")
        score.feature_metadata = {}
        score.save(update_fields=["feature_metadata"])
        self.assertEqual(self.client.get("/api/workbench/bonds/PIPELINE_001/").json()["shap_factors"], [])

    def test_alerts_do_not_invent_weather_events_for_demo_data(self):
        response = self.client.get("/api/alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alerts"], [])
        self.assertFalse(response.json()["weather_forecasts_connected"])

    def test_how_it_works_reports_demo_and_missing_evidence_separately(self):
        PCRScore.objects.filter(bond=self.bond).update(model_version="bootstrap-v1.0.0")
        response = self.client.get("/api/workflow/status/")
        self.assertEqual(response.status_code, 200)
        workflow = response.json()
        self.assertEqual(workflow["satellite"]["observed_count"], 0)
        self.assertEqual(workflow["risk"]["demo_count"], 1)
        self.assertEqual(workflow["risk"]["non_demo_count"], 0)
        self.assertEqual(workflow["risk"]["feature_count"], 20)
        self.assertFalse(workflow["pricing"]["individual_market_yields_connected"])
        self.assertFalse(workflow["alerts"]["weather_forecasts_connected"])
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demo estimates only")
        self.assertContains(response, "Awaiting real imagery")

    def test_pcrs_feature_audit_lists_exact_schema_without_strong_claims(self):
        from risk_scoring.feature_pipeline import FeatureEngineeringPipeline

        response = self.client.get("/api/pcrs/features/", {"bond_id": self.bond.bond_id})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        names = [feature["name"] for group in report["groups"] for feature in group["features"]]
        self.assertEqual(len(names), 20)
        self.assertEqual(set(names), set(FeatureEngineeringPipeline().all_feature_cols))
        self.assertEqual(report["coverage"][0]["available"], 1)
        self.assertIn("1 recorded/unverified", report["coverage"][0]["basis"])
        self.assertFalse(report["independently_validated_loss_model"])
        self.assertNotIn("Strong", str(report["coverage"]))
        self.assertEqual(report["bond"]["bond_id"], self.bond.bond_id)

    def test_recomputed_scores_keep_demo_input_status(self):
        PCRScore.objects.filter(bond=self.bond).update(
            model_version="v2.0.0-proxy",
            feature_metadata={"provenance": {"primary_status": "demo"}},
        )
        report = self.client.get("/api/workflow/status/").json()
        self.assertEqual(report["risk"]["demo_count"], 1)
        self.assertEqual(report["risk"]["non_demo_count"], 0)

    def test_synthetic_satellite_flags_do_not_become_review_alerts(self):
        GreenwashFlag.objects.filter(bond=self.bond).update(
            verification_status="verifiable", is_inconsistent=True,
            raw_ee_metadata={"method": "synthetic"},
        )
        self.assertEqual(self.client.get("/api/alerts/").json()["alerts"], [])

    def test_real_stored_inconsistency_produces_a_deterministic_alert(self):
        GreenwashFlag.objects.filter(bond=self.bond).update(
            verification_status="verifiable", is_inconsistent=True,
            raw_ee_metadata={"source": "gee"},
        )
        first = self.client.get("/api/alerts/").json()["alerts"]
        second = self.client.get("/api/alerts/").json()["alerts"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["kind"], "satellite")
        self.assertEqual(first[0]["bond_id"], self.bond.bond_id)

    def test_newer_unverifiable_result_replaces_older_satellite_alert(self):
        GreenwashFlag.objects.filter(bond=self.bond).update(
            verification_status="verifiable", is_inconsistent=True,
            raw_ee_metadata={"source": "gee"},
        )
        GreenwashFlag.objects.create(
            bond=self.bond, verification_status="unverifiable", ndvi_change=0,
            satellite_land_use="unknown", claimed_project_type="water", confidence=0,
        )
        self.assertEqual(self.client.get("/api/alerts/").json()["alerts"], [])
