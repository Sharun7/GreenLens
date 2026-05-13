# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/feature_pipeline.py — Feature engineering pipeline for the PCRS model.

Loads bond + hazard data from the Django ORM, engineers features,
and returns (X, y, feature_names) ready for XGBoost training.
"""
import logging
import math
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger("greenlens.feature_pipeline")

# ── Category vulnerability mapping ────────────────────────────────────────────
CATEGORY_VULNERABILITY: dict[str, float] = {
    "solar":        0.30,
    "wind":         0.40,
    "water":        0.70,
    "transport":    0.60,
    "building":     0.50,
    "reforestation": 0.50,
    "other":        0.40,
}

# ── IPCC warming trend ordinal (1 = low warming, 5 = very high warming) ───────
# Source: IPCC AR6 Chapter 4 regional projections (RCP8.5 2041–2060 vs 1995–2014)
CLIMATE_TREND: dict[str, int] = {
    "AND": 3, "ARG": 3, "AUS": 4, "AUT": 3, "BGD": 5, "BLR": 3, "BEL": 2,
    "BEN": 5, "BMU": 2, "BOL": 4, "BRA": 4, "VGB": 2, "BFA": 5, "CAN": 4,
    "CYM": 2, "CHL": 3, "CHN": 3, "COL": 3, "CRI": 3, "HRV": 3, "CYP": 4,
    "CZE": 3, "CIV": 5, "DNK": 2, "DOM": 3, "ECU": 3, "EGY": 5, "EST": 3,
    "FJI": 3, "FIN": 3, "FRA": 3, "GEO": 3, "DEU": 2, "GRC": 4, "GTM": 3,
    "GGY": 2, "GNB": 5, "HND": 4, "HUN": 3, "ISL": 2, "IND": 5, "IDN": 4,
    "IRL": 2, "IMN": 2, "ISR": 4, "ITA": 4, "JPN": 3, "JEY": 2, "JOR": 4,
    "KAZ": 4, "KEN": 4, "KOR": 3, "LAO": 4, "LVA": 3, "LIE": 3, "LTU": 3,
    "LUX": 2, "MYS": 4, "MLI": 5, "MLT": 4, "MHL": 3, "MRT": 5, "MEX": 4,
    "MNG": 4, "MAR": 4, "NAM": 4, "NLD": 2, "NZL": 3, "NER": 5, "NGA": 5,
    "NOR": 2, "PAK": 5, "PAN": 3, "PRY": 4, "PER": 4, "PHL": 4, "POL": 3,
    "PRT": 4, "QAT": 5, "ROM": 3, "RUS": 3, "REU": 3, "SAU": 5, "SEN": 5,
    "SRB": 3, "SYC": 3, "SGP": 4, "SVK": 3, "SVN": 3, "ZAF": 4, "ESP": 4,
    "SDN": 5, "SWE": 2, "CHE": 3, "TWN": 3, "THA": 4, "TGO": 5, "TUR": 4,
    "UKR": 3, "ARE": 5, "GBR": 2, "USA": 3, "URY": 3, "UZB": 4,
    "VEN": 4, "VNM": 4, "WLD": 3,
}
DEFAULT_CLIMATE_TREND = 3

# ── Coastal reference points (lat, lon) for proximity check ───────────────────
# ~100 points distributed around world coastlines
COASTAL_REFERENCE_POINTS: list[tuple[float, float]] = [
    # North America
    (40.7, -74.0), (34.0, -118.2), (25.8, -80.2), (29.8, -95.4),
    (47.6, -122.3), (45.5, -73.6), (43.7, -79.4), (49.3, -123.1),
    # South America
    (-23.5, -43.2), (-33.4, -70.6), (-34.9, -56.2), (-12.0, -77.0),
    (-3.7, -38.5), (-8.1, -34.9),
    # Europe
    (51.5, -0.1), (48.9, 2.3), (52.4, 13.4), (41.9, 12.5),
    (40.4, -3.7), (38.7, -9.1), (53.6, 10.0), (59.9, 10.7),
    (55.7, 12.6), (37.9, 23.7), (41.0, 29.0), (59.4, 24.7),
    (56.9, 24.1), (54.7, 25.3), (50.1, 14.4),
    # Africa
    (30.1, 31.2), (-33.9, 18.4), (-4.3, 15.3), (6.4, 3.4),
    (5.6, -0.2), (14.7, -17.5), (-25.9, 32.6), (-18.9, 47.5),
    # Middle East / South Asia
    (25.2, 55.3), (24.7, 46.7), (29.4, 47.9), (23.6, 58.6),
    (18.0, 49.0), (23.6, 90.4), (22.3, 91.8), (17.4, 78.5),
    (19.1, 72.9), (13.1, 80.3), (9.9, 76.3), (12.9, 74.9),
    # Southeast Asia / Pacific
    (1.3, 103.8), (3.1, 101.7), (14.6, 121.0), (10.8, 106.7),
    (16.1, 108.2), (13.7, 100.5), (5.6, 95.3), (-6.2, 106.8),
    (-7.2, 112.7), (-8.8, 115.2), (22.3, 114.2), (22.5, 120.0),
    (31.2, 121.5), (37.6, 121.0), (35.7, 139.7), (34.7, 135.5),
    (37.2, 126.8), (-37.8, 144.9), (-33.9, 151.2), (-27.5, 153.0),
    (-36.9, 174.8), (-41.3, 174.8),
    # Caribbean / Central America
    (18.5, -69.9), (18.0, -76.8), (10.7, -61.5), (17.1, -61.8),
    (9.1, -79.4), (9.9, -84.1), (14.1, -87.2),
]
COASTAL_THRESHOLD_KM = 200.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_coastal(lat: float, lon: float, threshold_km: float = COASTAL_THRESHOLD_KM) -> bool:
    """Return True if the coordinate is within threshold_km of a coastline reference point."""
    if lat == 0.0 and lon == 0.0:
        return False
    for clat, clon in COASTAL_REFERENCE_POINTS:
        if _haversine_km(lat, lon, clat, clon) <= threshold_km:
            return True
    return False


class FeatureEngineeringPipeline:
    """
    Loads bond + hazard data from the Django ORM and engineers features
    for XGBoost PCRS training.

    Usage:
        pipeline = FeatureEngineeringPipeline()
        X, y, feature_names = pipeline.fit_transform()
        # or for a single bond:
        X_single, _, feature_names = pipeline.transform_single(bond_id=42)
    """

    def __init__(self, scaler: Optional[MinMaxScaler] = None):
        self.scaler = scaler or MinMaxScaler()
        self.feature_names_: list[str] = []
        self._fitted = False

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_dataframe(self, bond_ids: Optional[list[int]] = None) -> pd.DataFrame:
        """
        Load GreenBond + ClimateHazardData from the ORM into a DataFrame.
        Uses WorldBankClimateFetcher as fallback for bonds without hazard data.
        """
        # Import inside method to allow module-level import without Django setup
        from data_ingestion.models import GreenBond, ClimateHazardData
        from greenlens.data.worldbank_climate import WorldBankClimateFetcher

        wb_fetcher = WorldBankClimateFetcher()

        qs = GreenBond.objects.all()
        if bond_ids:
            qs = qs.filter(pk__in=bond_ids)

        # Build a dict of latest hazard data per bond
        hazard_qs = (
            ClimateHazardData.objects
            .filter(bond__in=qs)
            .order_by("bond_id", "-data_date")
            .distinct("bond_id")
        )
        hazard_map: dict[int, ClimateHazardData] = {h.bond_id: h for h in hazard_qs}

        records = []
        for bond in qs.iterator(chunk_size=200):
            h = hazard_map.get(bond.pk)

            if h is not None:
                flood    = float(h.flood_risk_index)
                heat     = float(h.heat_stress_index)
                drought  = float(h.drought_spei)
                carbon   = float(h.carbon_intensity_score) if h.carbon_intensity_score is not None else 0.35
                policy   = float(h.policy_risk_score)      if h.policy_risk_score      is not None else 0.45
                transit  = float(h.transition_risk_score)  if h.transition_risk_score  is not None else 0.40
            else:
                # Fallback: WorldBank country-level data
                iso3 = self._iso3_from_country(bond.country)
                wb = wb_fetcher.get_all_hazards(iso3)
                flood   = wb["flood_risk"]
                heat    = wb["heat_stress"]
                drought = wb["drought_spei"]
                from data_ingestion.extended_risk_fetcher import ExtendedRiskFetcher
                er = ExtendedRiskFetcher()
                er_scores = er.get_all(iso3)
                carbon  = er_scores["carbon_intensity_score"]
                policy  = er_scores["policy_risk_score"]
                transit = er_scores["transition_risk_score"]

            records.append({
                "bond_pk":             bond.pk,
                "bond_id":             bond.bond_id,
                "country":             bond.country,
                "iso3":                self._iso3_from_country(bond.country),
                "lat":                 float(bond.lat or 0.0),
                "lon":                 float(bond.lon or 0.0),
                "project_category":    bond.project_category,
                "bond_maturity_years": int(bond.bond_maturity_years or 7),
                "flood_risk_index":    flood,
                "heat_stress_index":   heat,
                "drought_spei":        drought,
                "carbon_intensity_score": carbon,
                "policy_risk_score":      policy,
                "transition_risk_score":  transit,
            })

        if not records:
            logger.warning("FeatureEngineeringPipeline: no data loaded")
            return pd.DataFrame()

        return pd.DataFrame(records)

    # ── Feature engineering ───────────────────────────────────────────────────

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived features to the DataFrame in-place."""

        # 1. Drought severity (SPEI → positive severity, 0 = no drought)
        df["drought_severity"] = df["drought_spei"].apply(
            lambda s: max(0.0, -s / 3.0)   # SPEI -3 → 1.0; positive SPEI → 0
        )

        # 2. Composite hazard (weighted sum)
        df["composite_hazard"] = (
            df["flood_risk_index"] * 0.40
            + df["heat_stress_index"] * 0.35
            + df["drought_severity"] * 0.25
        ).clip(0.0, 1.0)

        # 3. Is coastal
        df["is_coastal"] = df.apply(
            lambda r: float(is_coastal(r["lat"], r["lon"])), axis=1
        )

        # 4. Climate trend (IPCC ordinal 1–5)
        df["climate_trend"] = df["iso3"].map(
            lambda x: CLIMATE_TREND.get(str(x).upper(), DEFAULT_CLIMATE_TREND)
        ).astype(float)

        # 5. Maturity exposure
        df["maturity_exposure"] = df.apply(
            lambda r: math.log(max(1, r["bond_maturity_years"])) * r["composite_hazard"],
            axis=1,
        )

        # 6. Category vulnerability
        df["category_vulnerability"] = df["project_category"].map(
            lambda c: CATEGORY_VULNERABILITY.get(str(c).lower(), 0.40)
        )

        # 7. Interaction: hazard × vulnerability
        df["hazard_x_vulnerability"] = df["composite_hazard"] * df["category_vulnerability"]

        # 8. Coastal × flood interaction
        df["coastal_flood"] = df["is_coastal"] * df["flood_risk_index"]

        return df

    # ── One-hot encoding ──────────────────────────────────────────────────────

    @staticmethod
    def _one_hot_category(df: pd.DataFrame) -> pd.DataFrame:
        cats = ["solar", "wind", "water", "transport", "building", "reforestation", "other"]
        for c in cats:
            df[f"cat_{c}"] = (df["project_category"] == c).astype(float)
        return df

    # ── Feature selection ─────────────────────────────────────────────────────

    NUMERIC_FEATURES = [
        "flood_risk_index",
        "heat_stress_index",
        "drought_severity",
        "composite_hazard",
        "is_coastal",
        "climate_trend",
        "maturity_exposure",
        "category_vulnerability",
        "hazard_x_vulnerability",
        "coastal_flood",
        "carbon_intensity_score",   # NEW: EDGAR CO2 intensity
        "policy_risk_score",        # NEW: World Bank Governance
        "transition_risk_score",    # NEW: NDC + fossil fuel dependency
    ]
    CATEGORY_FEATURES = [
        "cat_solar", "cat_wind", "cat_water", "cat_transport",
        "cat_building", "cat_reforestation", "cat_other",
    ]

    @property
    def all_feature_cols(self) -> list[str]:
        return self.NUMERIC_FEATURES + self.CATEGORY_FEATURES

    # ── Public API ────────────────────────────────────────────────────────────

    def fit_transform(
        self, bond_ids: Optional[list[int]] = None
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """
        Load data, engineer features, fit scaler, and return (X, y, feature_names).

        y is synthesised as composite_hazard * 100 (PCRS proxy 0–100).
        """
        df = self._load_dataframe(bond_ids)
        if df.empty:
            raise ValueError("No bond/hazard data available for training")

        df = self._engineer_features(df)
        df = self._one_hot_category(df)

        feature_cols = self.all_feature_cols
        X_raw = df[feature_cols].fillna(0.0).values.astype(float)
        y = (df["composite_hazard"] * 100.0).values.astype(float)

        # Fit and transform numeric features; pass binary/ordinal cols through
        n_numeric = len(self.NUMERIC_FEATURES)
        X_numeric = self.scaler.fit_transform(X_raw[:, :n_numeric])
        X = np.hstack([X_numeric, X_raw[:, n_numeric:]])

        self.feature_names_ = feature_cols
        self._fitted = True
        self._df_index = df["bond_pk"].tolist()

        logger.info("Pipeline fit_transform: %d samples, %d features", len(X), len(feature_cols))
        return X, y, feature_cols

    def transform_single(self, bond_id: int) -> tuple[np.ndarray, None, list[str]]:
        """
        Transform a single bond (by DB pk) for inference.
        Scaler must already be fitted (call fit_transform first or load from joblib).
        """
        if not self._fitted:
            raise RuntimeError("Pipeline not fitted. Call fit_transform() first.")

        df = self._load_dataframe(bond_ids=[bond_id])
        if df.empty:
            raise ValueError(f"Bond pk={bond_id} not found")

        df = self._engineer_features(df)
        df = self._one_hot_category(df)

        feature_cols = self.all_feature_cols
        X_raw = df[feature_cols].fillna(0.0).values.astype(float)

        n_numeric = len(self.NUMERIC_FEATURES)
        X_numeric = self.scaler.transform(X_raw[:, :n_numeric])
        X = np.hstack([X_numeric, X_raw[:, n_numeric:]])

        return X, None, feature_cols

    # ── ISO3 helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _iso3_from_country(country: str) -> str:
        """
        Extract a 3-letter ISO3 code from the bond's country string.
        The CBI CSV stores full country names; we try to map common ones.
        """
        from data_ingestion.management.commands.load_cbi_bonds import COUNTRY_NAME_MAP

        name_to_iso: dict[str, str] = {
            "andorra, principality of": "AND",
            "argentina": "ARG", "australia": "AUS", "austria": "AUT",
            "bangladesh": "BGD", "belarus, rep. of": "BLR", "belgium": "BEL",
            "benin": "BEN", "bolivia": "BOL", "brazil": "BRA",
            "burkina faso": "BFA", "canada": "CAN", "cayman islands": "CYM",
            "chile": "CHL", "china, p.r.: mainland": "CHN",
            "china, p.r.: hong kong": "HKG", "china, p.r.: macao": "MAC",
            "colombia": "COL", "costa rica": "CRI", "croatia, rep. of": "HRV",
            "cyprus": "CYP", "czech rep.": "CZE", "côte d'ivoire": "CIV",
            "denmark": "DNK", "dominican rep.": "DOM", "ecuador": "ECU",
            "egypt, arab rep. of": "EGY", "estonia, rep. of": "EST",
            "fiji, rep. of": "FJI", "finland": "FIN", "france": "FRA",
            "georgia": "GEO", "germany": "DEU", "greece": "GRC",
            "guatemala": "GTM", "guernsey": "GGY", "guinea-bissau": "GNB",
            "honduras": "HND", "hungary": "HUN", "iceland": "ISL",
            "india": "IND", "indonesia": "IDN", "ireland": "IRL",
            "isle of man": "IMN", "israel": "ISR", "italy": "ITA",
            "japan": "JPN", "jersey": "JEY", "jordan": "JOR",
            "kazakhstan, rep. of": "KAZ", "kenya": "KEN", "korea, rep. of": "KOR",
            "lao people's dem. rep.": "LAO", "latvia": "LVA",
            "liechtenstein": "LIE", "lithuania": "LTU", "luxembourg": "LUX",
            "malaysia": "MYS", "mali": "MLI", "malta": "MLT",
            "marshall islands, rep. of the": "MHL", "mauritius": "MUS",
            "mexico": "MEX", "mongolia": "MNG", "morocco": "MAR",
            "namibia": "NAM", "netherlands, the": "NLD", "new zealand": "NZL",
            "niger": "NER", "nigeria": "NGA", "norway": "NOR",
            "pakistan": "PAK", "panama": "PAN", "paraguay": "PRY",
            "peru": "PER", "philippines": "PHL", "poland, rep. of": "POL",
            "portugal": "PRT", "qatar": "QAT", "romania": "ROM",
            "russian federation": "RUS", "réunion": "REU",
            "saudi arabia": "SAU", "senegal": "SEN", "serbia, rep. of": "SRB",
            "seychelles": "SYC", "singapore": "SGP", "slovak rep.": "SVK",
            "slovenia, rep. of": "SVN", "south africa": "ZAF", "spain": "ESP",
            "sudan": "SDN", "sweden": "SWE", "switzerland": "CHE",
            "taiwan province of china": "TWN", "thailand": "THA", "togo": "TGO",
            "türkiye, rep. of": "TUR", "ukraine": "UKR",
            "united arab emirates": "ARE", "united kingdom": "GBR",
            "united states": "USA", "uruguay": "URY",
            "uzbekistan, rep. of": "UZB", "venezuela, rep. bolivariana de": "VEN",
            "vietnam": "VNM", "world": "WLD",
            "bermuda": "BMU", "british virgin islands": "VGB",
        }
        key = (country or "").strip().lower()
        return name_to_iso.get(key, key[:3].upper() if len(key) >= 3 else "UNK")
