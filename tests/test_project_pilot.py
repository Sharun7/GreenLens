from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test import TestCase
from copy import deepcopy

from data_ingestion.pilot import boundary_hash, validate_boundary


BOUNDARY = {"type": "Polygon", "coordinates": [[[-100, 30], [-99.99, 30], [-99.99, 30.01], [-100, 30.01], [-100, 30]]]}


class PilotGeometryTests(SimpleTestCase):
    def test_real_polygons_are_required(self):
        self.assertGreater(validate_boundary(BOUNDARY).area, 0)
        self.assertEqual(len(boundary_hash(BOUNDARY)), 64)
        for boundary in (
            {"type": "Point", "coordinates": [-100, 30]},
            {"type": "Polygon", "coordinates": []},
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
        ):
            with self.subTest(boundary=boundary), self.assertRaises(ValidationError):
                validate_boundary(boundary)

    def test_optical_quality_requires_real_measurements_and_coverage(self):
        from greenwash_detector.pilot_evidence import optical_quality

        values = {period: {"scene_count": 5, "ndvi": 0.4, "ndmi": 0.2, "observed_fraction": 0.95} for period in ("before", "after")}
        self.assertEqual(optical_quality(values), "observed")
        values["after"]["ndvi"] = None
        self.assertEqual(optical_quality(values), "unavailable")
        values["after"]["ndvi"] = 0.4
        values["after"]["observed_fraction"] = 0.1
        self.assertEqual(optical_quality(values), "unavailable")


class PilotImportTests(TestCase):
    def test_pilot_workspace_is_public_but_boundary_reviews_require_authorization(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from data_ingestion.models import PilotProject, PilotOutcome

        project = PilotProject.objects.create(
            source_id="USPVDB-TEST", name="Test facility", country="United States", region="TX",
            boundary=BOUNDARY, boundary_sha256=boundary_hash(BOUNDARY), source_url="https://example.com/source", source_version="test",
            source_metadata={"p_county": "Travis"},
        )
        response = self.client.get(reverse("dashboard:project_pilot"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project evidence pilot")
        payload = {"source_id": project.source_id, "boundary_sha256": project.boundary_sha256,
                   "review_status": "approved", "notes": "Reviewed against the independent source imagery."}
        self.assertEqual(self.client.post("/pilot/review/", payload).status_code, 403)
        reviewer = get_user_model().objects.create_user(username="pilot-reviewer", is_staff=True, is_superuser=True)
        self.client.force_login(reviewer)
        self.assertEqual(self.client.post("/pilot/review/", {**payload, "boundary_sha256": "stale"}).status_code, 409)
        self.assertEqual(self.client.post("/pilot/review/", payload).status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.reviewed_by, reviewer)
        self.assertEqual(project.review_status, "approved")
        self.assertEqual(PilotOutcome.objects.count(), 0)

    def test_import_is_idempotent_and_does_not_create_bonds_or_labels(self):
        from data_ingestion.models import GreenBond, PilotOutcome, PilotProject
        from data_ingestion.pilot import import_official_projects

        dataset = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": BOUNDARY,
            "properties": {"case_id": 1, "p_name": "Source fixture", "p_state": "TX", "p_dig_conf": 4,
                           "p_sys_type": "ground", "p_year": 2020},
        }]}
        self.assertEqual(import_official_projects(dataset, "test-source", "a" * 64, limit=1)["created"], 1)
        self.assertEqual(import_official_projects(dataset, "test-source", "a" * 64, limit=1)["unchanged"], 1)
        expanded = deepcopy(dataset)
        extra = deepcopy(expanded["features"][0])
        extra["properties"]["case_id"] = 2
        expanded["features"].append(extra)
        self.assertEqual(import_official_projects(expanded, "new-release", "c" * 64, limit=1)["unchanged"], 1)
        self.assertEqual(PilotProject.objects.get().source_id, "USPVDB-1")
        changed = deepcopy(dataset)
        changed["features"][0]["geometry"]["coordinates"][0][1][0] = -99.98
        self.assertEqual(import_official_projects(changed, "test-source", "b" * 64, limit=1)["boundary_conflicts"], ["USPVDB-1"])
        self.assertEqual(PilotProject.objects.get().review_status, "pending")
        self.assertEqual(GreenBond.objects.count(), 0)
        self.assertEqual(PilotOutcome.objects.count(), 0)


class PilotEvaluationTests(SimpleTestCase):
    def rows(self):
        from risk_scoring.pilot_evaluation import FEATURES

        rows = []
        for part, size, feature_date, outcome_date, available, county in (
            ("train", 12, "2019-01-01", "2019-06-01", "2019-07-01", "Travis"),
            ("cal", 10, "2021-01-01", "2021-06-01", "2021-07-01", "Travis"),
            ("time", 5, "2023-01-01", "2023-06-01", "2023-07-01", "Travis"),
            ("geo", 5, "2023-01-01", "2023-06-01", "2023-07-01", "Ector"),
        ):
            for index in range(size):
                rows.append({
                    "project_id": f"TEST-{part}-{index}", "county": county,
                    "boundary_reviewed": True, "label_reviewed": True, "independently_observed": True,
                    "feature_date": feature_date, "outcome_date": outcome_date, "label_available_on": available,
                    "damage_fraction": index / size, "label_source_url": "https://example.com/test-only-labels",
                    "label_method": "Independent observed damage records - unit fixture only",
                    "features": {name: index / size for name in FEATURES},
                    "feature_provenance": {name: {"kind": "observed", "source_url": "https://example.com/test-only-features", "available_on": feature_date} for name in FEATURES},
                })
        return rows

    def test_evaluation_keeps_geo_time_and_calibration_separate(self):
        from risk_scoring.pilot_evaluation import evaluate_pilot

        model, report = evaluate_pilot(self.rows(), "2020-01-01", "2022-01-01", ["Ector"])
        self.assertEqual(model.__class__.__name__, "XGBRegressor")
        sets = [set(report["split_project_ids"][name]) for name in ("train", "calibration", "temporal_test", "geographic_test")]
        self.assertEqual(len(set.union(*sets)), sum(map(len, sets)))
        self.assertEqual(report["geographic_test"]["n"], 5)
        self.assertIn("empirical_coverage", report["temporal_test"])
        self.assertEqual(report["status"], "evaluated_not_promoted")

    def test_unreviewed_proxy_future_features_and_repeated_projects_are_blocked(self):
        from risk_scoring.pilot_evaluation import validate_rows

        for mutation in ("unreviewed", "synthetic", "future", "repeated"):
            rows = self.rows()
            if mutation == "unreviewed":
                rows[0]["label_reviewed"] = False
            elif mutation == "synthetic":
                rows[0]["label_method"] = "synthetic proxy"
            elif mutation == "future":
                rows[0]["feature_provenance"]["s2_ndvi"]["available_on"] = "2030-01-01"
            else:
                rows.append(deepcopy(rows[0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_rows(rows)

    def test_conformal_quantile_uses_finite_sample_rank(self):
        from risk_scoring.pilot_evaluation import conformal_radius

        self.assertEqual(conformal_radius(list(range(10)), [0] * 10, 0.1), 9.0)
        with self.assertRaises(ValueError):
            conformal_radius([0, 1], [0, 0], 0.1)

    def test_encoder_benchmark_requires_common_frozen_test_projects(self):
        from risk_scoring.pilot_benchmark import benchmark_encoders
        from risk_scoring.pilot_evaluation import evaluate_pilot

        rows = self.rows()
        _, evaluation = evaluate_pilot(rows, "2020-01-01", "2022-01-01", ["Ector"])
        ids = evaluation["split_project_ids"]["temporal_test"] + evaluation["split_project_ids"]["geographic_test"]
        bundles = [{"encoder": name, "weights_sha256": "a" * 64, "preprocessing_sha256": "b" * 64,
                    "checkpoint_url": "https://example.com/test-only-checkpoint", "license_url": "https://example.com/test-license",
                    "input_bands": ["red", "green", "blue"], "head_recipe": "Test fixture only",
                    "training_project_ids": evaluation["split_project_ids"]["train"],
                    "predictions": {identifier: 0.4 for identifier in ids}} for name in ("resnet18", "prithvi")]
        self.assertEqual(benchmark_encoders(rows, evaluation, bundles)["encoders"]["prithvi"]["n"], 10)
        bundles[1]["training_project_ids"] = ids
        with self.assertRaises(ValueError):
            benchmark_encoders(rows, evaluation, bundles)


class PilotFinanceGateTests(SimpleTestCase):
    def test_estimated_spreads_are_not_return_scenarios(self):
        from pricing_analysis.pilot_optimization import optimize_reviewed_portfolio

        with self.assertRaises(ValueError):
            optimize_reviewed_portfolio([[0.1, 0.2]] * 60, ["one", "two"], {"status": "bootstrap_synthetic"})

    def test_cvxpy_solution_preserves_budget_and_allocation_cap(self):
        from datetime import date, timedelta
        import numpy as np
        from pricing_analysis.pilot_optimization import optimize_reviewed_portfolio

        returns = np.random.default_rng(42).normal(0.001, 0.01, size=(90, 3))
        provenance = {"status": "reviewed_market_observations", "usage_rights_confirmed": True,
                      "reviewed_by": "test-fixture-only", "source_url": "https://example.com/test-only-market-data",
                      "frequency": "daily", "as_of": "2024-12-31",
                      "scenario_dates": [(date(2024, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(90)]}
        result = optimize_reviewed_portfolio(returns, ["one", "two", "three"], provenance, max_weight=0.5)
        self.assertAlmostEqual(sum(result["weights"].values()), 1, places=6)
        self.assertTrue(all(weight <= 0.500001 for weight in result["weights"].values()))
        with self.assertRaises(ValueError):
            optimize_reviewed_portfolio(returns, ["one", "two", "three"], provenance, max_weight=0.1)


class PilotClimateScenarioTests(SimpleTestCase):
    def test_reviewed_ensemble_compares_units_without_inventing_loss(self):
        from risk_scoring.pilot_scenarios import compare_climate_periods

        rows = []
        for model in ("test-model-1", "test-model-2", "test-model-3"):
            for variable, baseline, future, units in (("tasmax", 290, 292, "K"), ("pr", 0.00001, 0.00002, "kg m-2 s-1")):
                for scenario, start, end, value in (("historical", "1995-01-01", "2014-12-31", baseline), ("ssp245", "2031-01-01", "2050-12-31", future)):
                    rows.append({"project_id": "TEST", "model": model, "variable": variable, "scenario": scenario,
                                 "period_start": start, "period_end": end, "value": value, "units": units,
                                 "review_status": "reviewed", "reviewed_by": "test-only-fixture", "source_url": "https://example.com/test-only-climate",
                                 "dataset": "test-only", "downscaling_method": "test-only", "bias_correction": "test-only", "resolution_m": 25000})
        result = compare_climate_periods(rows)
        self.assertAlmostEqual(result["projects"]["TEST"]["tasmax"]["median_delta"], 2)
        self.assertAlmostEqual(result["projects"]["TEST"]["pr"]["median_delta"], 0.864)
        with self.assertRaises(ValueError):
            compare_climate_periods(rows[:4])