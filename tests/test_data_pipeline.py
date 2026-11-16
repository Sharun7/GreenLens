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


class OpticalThumbnailTests(SimpleTestCase):
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

    def test_home_map_uses_public_satellite_tiles_without_a_provider_key(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "server.arcgisonline.com/ArcGIS/rest/services/World_Imagery")
        self.assertContains(response, "https://tile.openstreetmap.org/")
        self.assertNotContains(response, "mt1.google.com/vt/")
        response = self.client.get(f"/bond/{self.bond.bond_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "server.arcgisonline.com/ArcGIS/rest/services/World_Imagery")
        self.assertNotContains(response, "mt1.google.com/vt/")

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
