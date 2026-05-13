from datetime import date

from django.test import Client, TestCase

from data_ingestion.models import GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


class AIFeaturesViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        bonds = []
        for index in range(1, 5):
            bond = GreenBond.objects.create(
                bond_id=f"BOND_{index:03d}",
                issuer_name=f"Issuer {index}",
                country="India" if index % 2 else "Germany",
                project_category="solar" if index % 2 else "wind",
                project_description="Test bond",
                bond_maturity_years=10 + index,
                issuance_date=date(2024, 1, index),
                currency="USD",
                amount_millions=50 + index,
                lat=10.0 + index,
                lon=76.0 + index,
                location_confidence="precise" if index == 1 else "city",
            )
            PCRScore.objects.create(
                bond=bond,
                score=35 + index * 10,
                flood_contribution=8 + index,
                heat_contribution=5 + index,
                drought_contribution=3 + index,
                model_version="v1.0.0",
                shap_values={
                    "flood_risk_index": 10 + index,
                    "heat_stress_index": 3 + index,
                    "drought_severity": 2 + index,
                },
            )
            PricingGap.objects.create(
                bond=bond,
                actual_spread_bps=420 + index * 10,
                predicted_spread_bps=390 + index * 5,
                data_source="test_feed",
            )
            bonds.append(bond)

        GreenwashFlag.objects.create(
            bond=bonds[0],
            verification_status="verifiable",
            ndvi_change=-0.22,
            satellite_land_use="bare_soil",
            claimed_project_type="reforestation",
            is_inconsistent=True,
            confidence=0.84,
            model_version="cnn-test",
        )

    def test_category_15_pages_render(self):
        for path in ["/ai/predictions/", "/ai/alerts/", "/ai/portfolio/", "/ai/regulatory/", "/future/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_portfolio_upload_generates_custom_optimization(self):
        response = self.client.post(
            "/ai/portfolio/",
            {
                "portfolio_name": "Professor Scenario",
                "portfolio_description": "Smoke test portfolio",
                "portfolio_input": "BOND_001, 2.5\nBOND_002, 1.5\nBOND_003, 3.0",
                "min_return_target": "4.2",
                "max_single_bond_allocation": "5.0",
                "geographic_diversification_required": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Professor Scenario")
        self.assertContains(response, "optimized successfully")
