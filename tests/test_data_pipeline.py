from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

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
