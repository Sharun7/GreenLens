from datetime import date
from unittest.mock import patch

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
                "max_single_bond_allocation": "25.0",
                "geographic_diversification_required": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Professor Scenario")
        self.assertContains(response, "Scenario report created")
        scenario = response.context["latest"]
        self.assertIsNone(scenario.current_return)
        self.assertIsNone(scenario.optimized_return)
        self.assertAlmostEqual(sum(row["amount_eur"] for row in scenario.optimized_bonds), 7.0)
        self.assertEqual(len({row["bond_id"] for row in scenario.optimized_bonds}), 4)
        self.assertTrue(all(row["amount_eur"] / 7.0 <= 0.25 for row in scenario.optimized_bonds))

    def test_portfolio_rejects_invalid_amounts_and_allocation_caps(self):
        from ai_features.models import PortfolioOptimization

        for amount in ("nan", "inf", "-5", "0", "not-a-number"):
            with self.subTest(amount=amount):
                response = self.client.post("/ai/portfolio/", {
                    "portfolio_input": f"BOND_001, {amount}", "max_single_bond_allocation": "100",
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form_error"])
        for cap in ("nan", "inf", "-1", "0", "101", "invalid", "5"):
            with self.subTest(cap=cap):
                response = self.client.post("/ai/portfolio/", {
                    "portfolio_input": "BOND_001, 2.5", "max_single_bond_allocation": cap,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form_error"])
        self.assertEqual(PortfolioOptimization.objects.count(), 0)

    def test_duplicate_portfolio_holdings_are_combined(self):
        response = self.client.post("/ai/portfolio/", {
            "portfolio_input": "BOND_001, 2.5\nBOND_001, 1.5", "max_single_bond_allocation": "100",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["latest"].current_bonds), 1)
        self.assertEqual(response.context["latest"].current_bonds[0]["amount_eur"], 4.0)

    @patch("ai_features.views._generate_real_predictions")
    def test_prediction_page_is_read_only_and_counts_latest_scores(self, generate):
        bond = GreenBond.objects.get(bond_id="BOND_001")
        PCRScore.objects.create(
            bond=bond, score=90, flood_contribution=1, heat_contribution=1,
            drought_contribution=1, model_version="test",
        )
        response = self.client.get("/ai/predictions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["systemic_prediction"]["scored_count"], 4)
        self.assertEqual(response.context["systemic_prediction"]["unviable_pct"], 75.0)
        self.assertContains(response, "not a forecast")
        self.assertNotContains(response, "Stranded Assets (EUR)")
        generate.assert_not_called()

    def test_exposure_sample_is_stable_and_counts_high_scores_without_alternatives(self):
        first = self.client.get("/portfolio/")
        second = self.client.get("/portfolio/")
        self.assertEqual(first.context["portfolio_bonds"], second.context["portfolio_bonds"])
        self.assertEqual(first.context["total_amount"], 4)
        self.assertEqual(first.context["high_risk_count"], 3)
        self.assertContains(first, "not your holdings or assets under management")

    @patch("ai_features.views._generate_real_alerts")
    def test_alert_page_does_not_generate_events_during_a_read(self, generate):
        response = self.client.get("/ai/alerts/", {"type": "greenwash"})
        self.assertEqual(response.status_code, 200)
        generate.assert_not_called()

    def test_portfolio_scenarios_are_private_to_the_submitting_session(self):
        response = self.client.post("/ai/portfolio/", {
            "portfolio_name": "Private client holdings", "portfolio_input": "BOND_001, 2.5",
            "max_single_bond_allocation": "100",
        })
        scenario_id = response.context["latest"].pk
        self.assertContains(self.client.get("/ai/portfolio/"), "Current Avg PCRS")
        self.assertEqual(self.client.get("/ai/api/v1/portfolios/").json()["count"], 1)
        stranger = Client(HTTP_HOST="localhost")
        self.assertContains(stranger.get("/ai/portfolio/"), "No portfolio scenario submitted")
        self.assertEqual(stranger.get("/ai/api/v1/portfolios/").json()["count"], 0)
        self.assertEqual(stranger.get(f"/ai/api/v1/portfolios/{scenario_id}/").status_code, 404)

    @patch("dashboard.ai_chat._get_gemini_model", side_effect=EnvironmentError("not configured"))
    def test_chat_uses_grounded_local_lookup_without_a_model_key(self, model):
        response = self.client.post("/api/chat/", {"message": "High risk solar bonds in India", "history": []}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        answer = response.json()["response"]
        self.assertIn("Local data lookup", answer)
        self.assertIn("BOND_003", answer)
        self.assertNotIn("BOND_002", answer)
        self.assertIn("estimated spread", answer)
        self.assertIn("Unverifiable", answer)
        self.assertNotIn("Database context unavailable", answer)

    @patch("dashboard.ai_chat.get_ai_response")
    def test_chat_rejects_invalid_payload_shapes(self, respond):
        for payload in ([], {"message": {}}, {"message": "hello", "history": {}},
                        {"message": "hello", "history": ["invalid"]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/chat/", payload, content_type="application/json").status_code, 400)
        respond.assert_not_called()

    def test_bias_report_does_not_treat_agreement_as_accuracy(self):
        from risk_scoring.bias_detection import BiasDetector

        report = BiasDetector().detect_cnn_classifier_bias()
        self.assertTrue(report["regional_stats"])
        for row in report["regional_stats"].values():
            self.assertIsNone(row["accuracy_pct"])
            self.assertEqual(row["bias_severity"], "UNVALIDATED")
            self.assertIsNone(row["agreement_pct"])

    @patch("risk_scoring.views.BiasDetector")
    def test_bias_report_download_is_a_server_json_attachment(self, detector):
        detector.return_value.run_full_analysis.return_value = {"validation": "unavailable"}
        response = self.client.get("/api/risk/bias-detection/", {"download": "1", "format": "json"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn('attachment; filename="greenlens_bias_report.json"', response["Content-Disposition"])
        self.assertEqual(response.json()["results"]["validation"], "unavailable")

    def test_anonymous_visitors_cannot_mutate_shared_research_records(self):
        for path in (
            "/api/risk/scores/predict/", "/api/risk/scores/batch_predict/",
            "/api/pricing/gaps/compute/", "/api/pricing/gaps/batch_compute/",
            "/api/pricing/analyser/fit/", "/api/pricing/analyser/analyse/",
            "/api/greenwash/flags/check/", "/api/greenwash/flags/batch_check/",
            "/api/risk/feedback/",
        ):
            with self.subTest(path=path):
                response = self.client.post(path, {}, content_type="application/json")
                self.assertIn(response.status_code, (401, 403))
