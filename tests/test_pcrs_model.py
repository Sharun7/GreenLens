import pytest
import pandas as pd
import joblib
import xgboost as xgb
import numpy as np
from datetime import date
from unittest.mock import Mock
from rest_framework.test import APIClient
from data_ingestion.models import ClimateHazardData, GreenBond
from risk_scoring.feature_pipeline import FeatureEngineeringPipeline
from risk_scoring.models import PCRScore
from risk_scoring.ml_engine import PCRSPredictor 
from pricing_analysis.analyser import PricingGapAnalyser
from django.urls import reverse

@pytest.fixture
def mock_bond(db):
    """Fixture to create a mock bond"""
    return GreenBond.objects.create(
        bond_id="TEST_BOND_PYTEST",
        issuer_name="Test Issuer",
        country="USA",
        project_category="solar",
        bond_maturity_years=5,
        amount_millions=100.0,
        lat=40.7128,
        lon=-74.0060,
        issuance_date=date(2021, 6, 1)
    )

@pytest.mark.django_db
def test_feature_pipeline_uses_latest_hazard(mock_bond):
    for hazard_date, flood in ((date(2025, 1, 1), 0.2), (date(2026, 1, 1), 0.8)):
        ClimateHazardData.objects.create(
            bond=mock_bond,
            data_date=hazard_date,
            flood_risk_index=flood,
            heat_stress_index=0.5,
            drought_spei=-0.5,
            source="nasa",
        )

    frame = FeatureEngineeringPipeline()._load_dataframe([mock_bond.pk])

    assert len(frame) == 1
    assert frame.iloc[0]["flood_risk_index"] == 0.8


@pytest.mark.django_db
def test_missing_extended_features_use_country_lookups_not_global_constants(mock_bond):
    from data_ingestion.extended_risk_fetcher import ExtendedRiskFetcher

    hazard = ClimateHazardData.objects.create(
        bond=mock_bond, data_date=date(2026, 1, 1), source="nasa",
        flood_risk_index=0.4, heat_stress_index=0.5, drought_spei=-0.5,
    )
    pipeline = FeatureEngineeringPipeline()
    expected = ExtendedRiskFetcher().get_all("USA")
    row = pipeline._load_dataframe([mock_bond.pk]).iloc[0]
    for feature, value in expected.items():
        assert row[feature] == value
    hazard.carbon_intensity_score = 0.0
    hazard.save(update_fields=["carbon_intensity_score"])
    assert pipeline._load_dataframe([mock_bond.pk]).iloc[0]["carbon_intensity_score"] == 0.0


@pytest.mark.django_db
def test_empty_bond_selection_does_not_load_the_entire_registry(mock_bond):
    assert FeatureEngineeringPipeline()._load_dataframe([]).empty


@pytest.mark.parametrize("country, expected", [
    ("China", "CHN"), ("South Korea", "KOR"), ("Bulgaria", "BGR"),
    ("United Kingdom", "GBR"), ("USA", "USA"), ("Not a country", "UNK"),
])
def test_feature_country_codes_are_real_iso3(country, expected):
    assert FeatureEngineeringPipeline._iso3_from_country(country) == expected


@pytest.fixture
def raw_feature_frame():
    return pd.DataFrame([{
        "flood_risk_index": 0.4, "heat_stress_index": 0.5, "drought_spei": -0.6,
        "carbon_intensity_score": 0.3, "policy_risk_score": 0.4,
        "transition_risk_score": 0.5, "lat": 9.5, "lon": 76.4,
        "bond_maturity_years": 10, "project_category": "solar", "iso3": "IND",
    }])


def test_engineered_formulas_and_one_hot_encoding(raw_feature_frame):
    pipeline = FeatureEngineeringPipeline()
    raw_feature_frame.loc[0, "drought_spei"] = -6
    raw_feature_frame.loc[0, "project_category"] = "UNKNOWN TYPE"
    frame = pipeline._one_hot_category(pipeline._engineer_features(raw_feature_frame))
    assert frame.iloc[0]["drought_severity"] == 1
    assert frame.iloc[0]["composite_hazard"] == pytest.approx(0.4 * 0.4 + 0.5 * 0.35 + 0.25)
    assert frame.iloc[0]["maturity_exposure"] == pytest.approx(np.log(10) * frame.iloc[0]["composite_hazard"])
    assert frame[pipeline.CATEGORY_FEATURES].iloc[0].sum() == 1
    assert frame.iloc[0]["cat_other"] == 1


@pytest.mark.parametrize("column, value", [
    ("flood_risk_index", np.nan), ("heat_stress_index", 1.5),
    ("policy_risk_score", -0.1), ("drought_spei", np.inf),
    ("bond_maturity_years", -5), ("lat", 91),
])
def test_invalid_features_do_not_become_zero_risk(raw_feature_frame, column, value):
    raw_feature_frame.loc[0, column] = value
    with pytest.raises(ValueError):
        FeatureEngineeringPipeline()._engineer_features(raw_feature_frame)


def test_coastal_feature_uses_geometry_not_nearby_city_names(monkeypatch, tmp_path):
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    from risk_scoring.geography import near_coastline

    dataset = tmp_path / "coastline.zip"
    dataset.touch()
    coastline = [LineString([(0, -10), (0, 10)])]
    monkeypatch.setattr("risk_scoring.geography.COASTLINE_PATH", dataset)
    monkeypatch.setattr("risk_scoring.geography._coastline_index", lambda: (coastline, STRtree(coastline)))
    assert near_coastline(0, 1, 200) is True
    assert near_coastline(0, 5, 200) is False


def test_missing_coastline_is_identified_as_a_heuristic(monkeypatch, tmp_path):
    from risk_scoring.geography import coastline_status, near_coastline

    monkeypatch.setattr("risk_scoring.geography.COASTLINE_PATH", tmp_path / "missing.zip")
    assert near_coastline(9.5, 76.4) is None
    assert coastline_status()["available"] is False


def test_training_is_country_held_out_and_scaler_does_not_see_test_data(monkeypatch, tmp_path):
    from sklearn.model_selection import GroupShuffleSplit
    from risk_scoring.ml_engine import train_pcrs_model

    pipeline = FeatureEngineeringPipeline()
    raw = np.arange(800, dtype=float).reshape(40, 20) / 800
    targets = np.linspace(10, 90, 40)
    groups = np.repeat(["IND", "USA", "DEU", "CHN", "BRA", "JPN", "FRA", "ZAF"], 5)
    pipeline._training_groups = groups.tolist()
    monkeypatch.setattr(pipeline, "prepare_training_data", lambda ids: (raw, targets, pipeline.all_feature_cols))
    monkeypatch.setattr("risk_scoring.ml_engine.FeatureEngineeringPipeline", lambda: pipeline)
    metrics = train_pcrs_model(output_dir=tmp_path, make_plot=False)
    training, _remaining = next(GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42).split(raw, targets, groups))
    saved = joblib.load(tmp_path / "scaler.pkl")
    assert np.allclose(saved.data_max_, raw[training, :13].max(axis=0))
    assert set(metrics["countries"]["train"]).isdisjoint(metrics["countries"]["test"])
    assert set(metrics["countries"]["validation"]).isdisjoint(metrics["countries"]["test"])
    assert metrics["target_kind"] == "hazard_derived_proxy"
    assert metrics["scaler_fit"] == "training_split_only"
    assert metrics["hyperparameters"]["n_jobs"] == 2
    monkeypatch.setattr("risk_scoring.ml_engine.FeatureEngineeringPipeline", FeatureEngineeringPipeline)
    predictor = PCRSPredictor(artifact_dir=tmp_path)
    assert predictor.model_version == "v2.0.0-proxy"
    with (tmp_path / "scaler.pkl").open("ab") as output:
        output.write(b"invalid")
    with pytest.raises(ValueError, match="checksum"):
        PCRSPredictor(artifact_dir=tmp_path)


def test_training_requires_explicit_consent_for_demo_hazards(monkeypatch, tmp_path):
    from risk_scoring.ml_engine import train_pcrs_model

    pipeline = FeatureEngineeringPipeline()
    pipeline.input_provenance_ = {1: {"primary_status": "demo"}}
    monkeypatch.setattr(pipeline, "prepare_training_data", lambda ids: (np.zeros((20, 20)), np.zeros(20), pipeline.all_feature_cols))
    monkeypatch.setattr("risk_scoring.ml_engine.FeatureEngineeringPipeline", lambda: pipeline)
    with pytest.raises(ValueError, match="allow-demo"):
        train_pcrs_model(output_dir=tmp_path, make_plot=False)
    assert not (tmp_path / "model.pkl").exists()


@pytest.mark.django_db
def test_pcrs_predictor_bounds(mock_bond, tmp_path, monkeypatch):
    ClimateHazardData.objects.create(
        bond=mock_bond, data_date=date(2026, 1, 1), source="nasa",
        flood_risk_index=0.6, heat_stress_index=0.4, drought_spei=-0.5,
    )
    pipeline = FeatureEngineeringPipeline()
    features, targets, names = pipeline.fit_transform([mock_bond.pk])
    model = xgb.XGBRegressor(n_estimators=4, max_depth=2, n_jobs=1, random_state=42)
    model.fit(features, targets)
    model_path, scaler_path = tmp_path / "model.pkl", tmp_path / "scaler.pkl"
    joblib.dump(model, model_path)
    joblib.dump(pipeline.scaler, scaler_path)
    monkeypatch.setattr("risk_scoring.ml_engine.MODEL_PATH", model_path)
    monkeypatch.setattr("risk_scoring.ml_engine.SCALER_PATH", scaler_path)
    monkeypatch.setattr("risk_scoring.ml_engine.VERSIONED_MODEL_DIR", tmp_path / "inactive")

    result = PCRSPredictor().predict(mock_bond.pk)
    score_obj = PCRScore.objects.get(bond=mock_bond)

    assert result["score"] == score_obj.score
    assert 0 <= score_obj.score <= 100
    assert len(names) == 20
    assert set(score_obj.shap_values) == set(names)
    assert set(score_obj.feature_metadata["features"]) == set(names)
    assert len(score_obj.feature_metadata["model_sha256"]) == 64
    reconstructed = score_obj.feature_metadata["base_value"] + sum(score_obj.shap_values.values())
    assert reconstructed == pytest.approx(score_obj.feature_metadata["raw_score"], abs=0.002)

@pytest.mark.django_db
def test_pricing_gap_analyser_required_fields(tmp_path, monkeypatch):
    """2. Test that PricingGapAnalyser.analyse() returns required fields"""
    monkeypatch.setattr("pricing_analysis.analyser.ANALYSER_MODEL_PATH", tmp_path / "pricing.pkl")
    analyser = PricingGapAnalyser()
    
    # Synthetic dataframe mapping real model traits
    df = pd.DataFrame({
        "pcrs_score": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 50, 60],
        "bond_maturity_years": [5]*12,
        "credit_rating_numeric": [4]*12,
        "actual_spread_bps": [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 180, 200]
    })
    
    analyser.fit(df)
    summary = analyser.get_market_summary()
    
    # Asserting all required fields exist
    assert "n_total" in summary
    assert "pct_underpricing_risk" in summary
    assert "mean_gap_bps" in summary

@pytest.mark.django_db
def test_api_bonds_returns_200():
    """3. Test that the /api/bonds/ endpoint returns 200 status"""
    client = APIClient()
    response = client.get('/api/bonds/')
    assert response.status_code == 200


@pytest.mark.django_db
def test_pricing_refresh_uses_regression_and_preserves_estimated_provenance(mock_bond, monkeypatch):
    from pricing_analysis.pricing_fetcher import BondPricingFetcher
    from pricing_analysis.views import _compute_gap_for_bond

    PCRScore.objects.create(
        bond=mock_bond, score=50, model_version="test", shap_values={},
        flood_contribution=0, heat_contribution=0, drought_contribution=0,
    )
    mock_bond.currency = "GBP"
    analyser = Mock()
    analyser.predict_spread.return_value = 180.0
    monkeypatch.setattr("pricing_analysis.analyser.PricingGapAnalyser", Mock(return_value=analyser))
    fetcher = BondPricingFetcher.__new__(BondPricingFetcher)
    fetcher.get_market_adjusted_spread = Mock(return_value=(210.0, True))

    gap, error = _compute_gap_for_bond(mock_bond, fetcher)

    assert error is None
    assert gap.actual_spread_bps == 210
    assert gap.predicted_spread_bps == 180
    assert gap.is_live is False
    assert gap.data_source == "market_adjusted_estimate"
    assert fetcher.get_market_adjusted_spread.call_args.kwargs["currency"] == "GBP"
    analyser.predict_spread.assert_called_once_with(50.0, 5.0)


@pytest.mark.django_db
def test_pricing_cannot_invent_a_prediction_without_a_risk_score(mock_bond):
    from pricing_analysis.tasks import refresh_bond_pricing

    fetcher = Mock()
    with pytest.raises(ValueError, match="no PCRScore"):
        refresh_bond_pricing(mock_bond, fetcher)
    fetcher.get_market_adjusted_spread.assert_not_called()


@pytest.mark.django_db
def test_pricing_review_alert_is_based_on_saved_gap(mock_bond):
    from dashboard.workflow import build_review_alerts
    from pricing_analysis.models import PricingGap

    PricingGap.objects.create(
        bond=mock_bond, actual_spread_bps=300, predicted_spread_bps=150,
        data_source="synthetic_table", is_live=False,
    )
    alerts = build_review_alerts()
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "pricing"
    assert "Estimated gap: +150.0 bps" == alerts[0]["impact"]
    assert "estimate" in alerts[0]["description"]


@pytest.mark.django_db
def test_batch_resume_scores_bonds_with_only_an_old_model_version(mock_bond, monkeypatch):
    from django.core.management import call_command

    PCRScore.objects.create(
        bond=mock_bond, score=40, model_version="bootstrap-v1.0.0", shap_values={},
        flood_contribution=0, heat_contribution=0, drought_contribution=0,
    )
    predictor = Mock(model_version="v2.0.0-proxy")
    monkeypatch.setattr("risk_scoring.ml_engine.PCRSPredictor", Mock(return_value=predictor))
    call_command("batch_score_bonds", only_missing=True)
    predictor.predict.assert_called_once_with(mock_bond.pk)


@pytest.mark.django_db
def test_zero_batch_limit_does_not_score_the_whole_registry(mock_bond, monkeypatch):
    from django.core.management import call_command

    predictor = Mock(model_version="v2.0.0-proxy")
    monkeypatch.setattr("risk_scoring.ml_engine.PCRSPredictor", Mock(return_value=predictor))
    call_command("batch_score_bonds", limit=0)
    predictor.predict.assert_not_called()


@pytest.mark.django_db
def test_zero_maturity_is_not_silently_replaced_with_seven_years(mock_bond):
    mock_bond.bond_maturity_years = 0
    mock_bond.save(update_fields=["bond_maturity_years"])
    ClimateHazardData.objects.create(
        bond=mock_bond, data_date=date(2026, 1, 1), source="nasa",
        flood_risk_index=0.4, heat_stress_index=0.5, drought_spei=-0.5,
    )
    with pytest.raises(ValueError, match="maturity"):
        FeatureEngineeringPipeline().prepare_training_data([mock_bond.pk])
