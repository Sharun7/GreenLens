from datetime import date

from django.test import Client, TestCase

from data_ingestion.models import ClimateHazardData, GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


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

    def test_data_reliability_api_still_available(self):
        response = self.client.get("/api/data-reliability/")
        self.assertEqual(response.status_code, 200)
