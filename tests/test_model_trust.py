from datetime import date

from django.test import Client, TestCase

from data_ingestion.models import ClimateHazardData, GreenBond
from risk_scoring.models import PCRScore


class ModelTrustPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        cls.bond = GreenBond.objects.create(
            bond_id="CYP_TRUST_001",
            issuer_name="Cyprus Green Finance",
            country="CYP",
            project_category="other",
            project_description="Trust page sample bond",
            bond_maturity_years=7,
            issuance_date=date(2024, 3, 15),
            currency="EUR",
            amount_millions=85,
            lat=35.1264,
            lon=33.4299,
            location_confidence="city",
        )
        ClimateHazardData.objects.create(
            bond=cls.bond,
            flood_risk_index=0.196,
            heat_stress_index=0.020,
            drought_spei=-0.008,
            data_date=date(2026, 4, 1),
            source="nasa",
        )
        PCRScore.objects.create(
            bond=cls.bond,
            score=31.8,
            flood_contribution=7.1,
            heat_contribution=-2.1,
            drought_contribution=1.4,
            model_version="v1.0.0",
            shap_values={
                "composite_hazard": 18.4,
                "maturity_exposure": 9.2,
                "flood_risk_index": 7.1,
                "hazard_x_vulnerability": 4.8,
                "heat_stress_index": -2.1,
                "drought_severity": 1.4,
            },
        )

    def test_model_trust_page_renders_live_sample(self):
        response = self.client.get("/model-trust/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Model Trust & Explainability")
        self.assertContains(response, "MSCI")
        self.assertContains(response, self.bond.bond_id)

    def test_model_depth_api_still_available(self):
        response = self.client.get("/api/model-depth/")
        self.assertEqual(response.status_code, 200)
