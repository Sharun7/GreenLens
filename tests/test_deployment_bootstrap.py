from datetime import date

from django.core.management import call_command
from django.test import Client, TestCase

from ai_features.models import ClimateScenario
from data_ingestion.models import ClimateHazardData, GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


class DeploymentBootstrapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        cls.bond = GreenBond.objects.create(
            bond_id="DEPLOY_001",
            issuer_name="Deployment Test Issuer",
            country="India",
            project_category="solar",
            project_description="Deployment bootstrap test bond",
            bond_maturity_years=9,
            issuance_date=date(2024, 4, 1),
            currency="USD",
            amount_millions=125,
            lat=20.5937,
            lon=78.9629,
            location_confidence="country",
        )
        ClimateScenario.objects.create(
            scenario_type="ssp2_4_5",
            description="SSP2-4.5",
            warming_by_2050=2.1,
            warming_by_2100=2.7,
        )

    def test_initialize_demo_data_backfills_missing_layers(self):
        call_command("initialize_demo_data", limit=10)

        self.assertEqual(ClimateHazardData.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(PCRScore.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(PricingGap.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(GreenwashFlag.objects.filter(bond=self.bond).count(), 1)

    def test_predictions_page_handles_unscored_database(self):
        response = self.client.get("/ai/predictions/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Climate Predictions")
