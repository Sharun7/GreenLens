from datetime import date

from django.test import Client, TestCase

from data_ingestion.models import GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


class DecisionImpactTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        cls.bond = GreenBond.objects.create(
            bond_id="QAT_TEST_001",
            issuer_name="Qatar Climate Finance",
            country="Qatar",
            project_category="solar",
            project_description="Test bond for decision impact",
            bond_maturity_years=12,
            issuance_date=date(2024, 2, 1),
            currency="USD",
            amount_millions=150,
            lat=25.33,
            lon=51.22,
            location_confidence="city",
        )
        cls.score = PCRScore.objects.create(
            bond=cls.bond,
            score=78.4,
            flood_contribution=9.0,
            heat_contribution=14.0,
            drought_contribution=11.0,
            model_version="v1.0.0",
            shap_values={
                "heat_stress_index": 14.0,
                "drought_severity": 11.0,
                "flood_risk_index": 9.0,
            },
        )
        cls.gap = PricingGap.objects.create(
            bond=cls.bond,
            actual_spread_bps=148.0,
            predicted_spread_bps=92.0,
            data_source="test_feed",
            is_live=True,
        )
        cls.flag = GreenwashFlag.objects.create(
            bond=cls.bond,
            verification_status="verifiable",
            ndvi_change=-0.18,
            satellite_land_use="bare_land",
            claimed_project_type="reforestation",
            is_inconsistent=True,
            confidence=0.87,
            model_version="cnn-test",
        )

    def test_decision_impact_page_renders(self):
        response = self.client.get("/decision-impact/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Real Decision Impact")
        self.assertContains(response, self.bond.bond_id)

    def test_feedback_submission_enters_review_flow(self):
        response = self.client.post(
            "/api/risk/feedback/",
            data={
                "bond_pk": self.bond.pk,
                "decision": "buy",
                "outcome": "model_error",
                "realized_loss_bps": 32.5,
                "notes": "Risk score overstated after manual review.",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        page = self.client.get("/decision-impact/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Public Review Log")
        self.assertContains(page, self.bond.bond_id)
