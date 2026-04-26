"""
pricing_analysis/analyser.py — PricingGapAnalyser

Trains a risk-adjusted expected spread model and detects mispriced green bonds.

Model:
    LinearRegression( [pcrs_score, bond_maturity_years, credit_rating_numeric]
                       → actual_spread_bps )

Mispricing definition:
    A bond is mispriced when |gap_bps| > 2 * cross-sectional std(gap_bps)
    where gap_bps = actual_spread_bps - predicted_spread_bps.

Usage:
    analyser = PricingGapAnalyser()
    analyser.fit_from_db()              # train on current DB data
    result = analyser.analyse(bond_id)  # score one bond
    summary = analyser.get_market_summary()
"""
import logging
import math
import os
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("greenlens.analyser")

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
ANALYSER_MODEL_PATH = MODEL_DIR / "pricing_analyser_v1.pkl"

# S&P/Fitch → numeric (lower = better credit quality → lower spread)
RATING_NUMERIC: dict[str, int] = {
    "AAA": 1, "AA+": 1, "AA": 2, "AA-": 2,
    "A+": 3,  "A": 3,   "A-": 3,
    "BBB+": 4, "BBB": 4, "BBB-": 4,
    "BB+": 5,  "BB": 5,  "BB-": 5,
    "B+": 6,   "B": 6,   "B-": 6,
}
DEFAULT_RATING_NUMERIC = 4  # BBB — used when credit rating is unavailable

# Features the model uses
FEATURE_COLS = ["pcrs_score", "bond_maturity_years", "credit_rating_numeric"]
TARGET_COL = "actual_spread_bps"

# Two-tailed mispricing threshold to capture ~20% of the distribution (1.28 std = 20%)
SIGMA_THRESHOLD = 1.3


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_training_df() -> pd.DataFrame:
    """
    Pull all bonds that have both a PCRScore and a PricingGap from the DB
    and return a clean DataFrame ready for model training.

    Returns empty DataFrame if not enough records exist.
    """
    from pricing_analysis.models import PricingGap
    from risk_scoring.models import PCRScore
    from django.db.models import OuterRef, Subquery

    # Latest PCRScore per bond (subquery)
    latest_score_sq = (
        PCRScore.objects
        .filter(bond=OuterRef("bond"))
        .order_by("-scored_at")
        .values("score")[:1]
    )

    # Fetch all PricingGap rows with pcrs_score annotated, ordered latest-first
    qs = (
        PricingGap.objects
        .select_related("bond")
        .order_by("bond_id", "-checked_at")   # order by bond FK then latest
        .annotate(pcrs_score=Subquery(latest_score_sq))
        .values(
            "bond_id",            # PricingGap FK (integer bond PK)
            "bond__bond_id",      # human-readable bond_id string
            "bond__issuer_name",
            "bond__project_category",
            "bond__bond_maturity_years",
            "actual_spread_bps",
            "pcrs_score",
        )
    )

    rows = list(qs)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "bond_id": "bond_pk",
        "bond__bond_id": "bond_id",
        "bond__issuer_name": "issuer_name",
        "bond__project_category": "project_category",
        "bond__bond_maturity_years": "bond_maturity_years",
    })

    # Keep only latest row per bond (already ordered latest-first)
    df = df.drop_duplicates(subset=["bond_pk"], keep="first")

    # Drop rows missing required fields
    df = df.dropna(subset=["pcrs_score", "actual_spread_bps", "bond_maturity_years"])

    if df.empty:
        return df

    # Default credit_rating_numeric to BBB (4) — no credit_rating on GreenBond yet
    df["credit_rating_numeric"] = DEFAULT_RATING_NUMERIC

    # Cast types
    df["pcrs_score"] = df["pcrs_score"].astype(float)
    df["bond_maturity_years"] = df["bond_maturity_years"].astype(float)
    df["actual_spread_bps"] = df["actual_spread_bps"].astype(float)
    df["credit_rating_numeric"] = df["credit_rating_numeric"].astype(float)

    return df


# ── Main class ────────────────────────────────────────────────────────────────

class PricingGapAnalyser:
    """
    Risk-adjusted spread regression + mispricing detector for green bonds.

    Attributes:
        model:   fitted sklearn LinearRegression
        scaler:  fitted StandardScaler for features
        gap_std: cross-sectional std of (actual - predicted) at fit time
        gap_mean: cross-sectional mean of gaps at fit time
        r2_train / r2_test: goodness-of-fit metrics
    """

    def __init__(self):
        self.model: Optional[LinearRegression] = None
        self.scaler: Optional[StandardScaler] = None
        self.gap_std: float = 20.0         # sensible default before fit
        self.gap_mean: float = 0.0
        self.r2_train: float = 0.0
        self.r2_test: float = 0.0
        self._n_train: int = 0

        # Try to load a previously saved model
        self._try_load()

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> dict:
        """
        Train the spread regression model on *df*.

        Args:
            df: DataFrame with columns
                [pcrs_score, bond_maturity_years, credit_rating_numeric,
                 actual_spread_bps]

        Returns:
            dict with r2_train, r2_test, n_samples, coefficients, intercept
        """
        required = FEATURE_COLS + [TARGET_COL]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

        df = df[required].dropna()
        if len(df) < 10:
            raise ValueError(
                f"Need at least 10 samples to fit — got {len(df)}. "
                "Run batch_compute to populate PricingGap records first."
            )

        X = df[FEATURE_COLS].values.astype(float)
        y = df[TARGET_COL].values.astype(float)

        # Train/test split (80/20)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Scale features
        self.scaler = StandardScaler()
        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s = self.scaler.transform(X_test)

        # Fit linear regression
        self.model = LinearRegression()
        self.model.fit(X_train_s, y_train)

        # Evaluate
        self.r2_train = float(r2_score(y_train, self.model.predict(X_train_s)))
        self.r2_test = float(r2_score(y_test, self.model.predict(X_test_s)))
        self._n_train = len(X_train)

        # Cross-sectional gap distribution at fit time
        X_all_s = self.scaler.transform(X)
        y_pred_all = self.model.predict(X_all_s)
        gaps = y - y_pred_all
        self.gap_mean = float(np.mean(gaps))
        self.gap_std = float(np.std(gaps))
        if self.gap_std < 1.0:
            self.gap_std = 1.0   # guard against degenerate case

        coef = dict(zip(FEATURE_COLS, self.model.coef_.tolist()))
        metrics = {
            "r2_train": round(self.r2_train, 4),
            "r2_test": round(self.r2_test, 4),
            "n_train": self._n_train,
            "n_test": len(X_test),
            "n_total": len(df),
            "coefficients": {k: round(v, 4) for k, v in coef.items()},
            "intercept": round(float(self.model.intercept_), 4),
            "gap_mean_bps": round(self.gap_mean, 2),
            "gap_std_bps": round(self.gap_std, 2),
        }
        logger.info(
            "PricingGapAnalyser fit complete: R²_train=%.3f R²_test=%.3f "
            "gap_std=%.1f bps n=%d",
            self.r2_train, self.r2_test, self.gap_std, len(df),
        )

        self._save()
        return metrics

    def fit_from_db(self) -> dict:
        """
        Convenience: build training data from DB and call fit().
        Returns the same metrics dict as fit().
        """
        df = _build_training_df()
        if df.empty:
            raise ValueError(
                "No training data found in DB. "
                "Ensure PCRScores and PricingGaps have been computed first."
            )
        return self.fit(df)

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict_spread(
        self,
        pcrs_score: float,
        bond_maturity_years: float,
        credit_rating_numeric: float = DEFAULT_RATING_NUMERIC,
    ) -> float:
        """
        Predict the fair-value spread (bps) for a single bond.
        Raises RuntimeError if model is not fitted.
        """
        self._require_fitted()
        X = np.array([[pcrs_score, bond_maturity_years, credit_rating_numeric]])
        X_s = self.scaler.transform(X)
        return float(self.model.predict(X_s)[0])

    def analyse(self, bond_id: int) -> dict:
        """
        Compute the pricing gap for bond with pk=bond_id and persist to DB.

        Steps:
          a. Fetch latest PCRScore + PricingGap from DB
          b. Predict fair-value spread via regression model
          c. gap_bps = actual_spread - predicted_spread
          d. Flag as mispriced if |gap_bps| > 2σ cross-sectional
          e. Update PricingGap record
          f. Return result dict

        Args:
            bond_id: GreenBond primary key (integer)

        Returns:
            {
              "bond_id": str,
              "bond_pk": int,
              "actual": float,
              "predicted": float,
              "gap": float,
              "gap_pct": float,
              "is_mispriced": bool,
              "interpretation": str,
              "sigma": float,   # how many sigma away
              "r2_model": float,
            }
        """
        self._require_fitted()

        from data_ingestion.models import GreenBond
        from risk_scoring.models import PCRScore
        from pricing_analysis.models import PricingGap

        # ── a. Load bond record ───────────────────────────────────────────────
        try:
            bond = GreenBond.objects.get(pk=bond_id)
        except GreenBond.DoesNotExist:
            raise ValueError(f"GreenBond pk={bond_id} not found")

        latest_score = (
            PCRScore.objects.filter(bond=bond).order_by("-scored_at").first()
        )
        if latest_score is None:
            raise ValueError(
                f"Bond {bond.bond_id} has no PCRScore. "
                "Run risk_scoring batch_predict first."
            )

        latest_gap = (
            PricingGap.objects.filter(bond=bond).order_by("-checked_at").first()
        )
        if latest_gap is None:
            raise ValueError(
                f"Bond {bond.bond_id} has no PricingGap. "
                "Run pricing batch_compute first."
            )

        # ── b. Predict spread ─────────────────────────────────────────────────
        pcrs = float(latest_score.score)
        maturity = float(bond.bond_maturity_years or 7)
        credit_num = float(DEFAULT_RATING_NUMERIC)

        predicted = self.predict_spread(pcrs, maturity, credit_num)
        actual = float(latest_gap.actual_spread_bps)

        # ── c. Gap ────────────────────────────────────────────────────────────
        gap = actual - predicted
        gap_pct = (gap / max(abs(predicted), 1.0)) * 100

        # ── d. Mispricing flag (2σ cross-sectional) ───────────────────────────
        sigma_distance = abs(gap - self.gap_mean) / self.gap_std
        is_mispriced = sigma_distance > SIGMA_THRESHOLD

        # ── e. Persist ────────────────────────────────────────────────────────
        # Update predicted spread and recompute gap on the existing record.
        # Use queryset .update() to bypass the model's save() hook (which uses
        # the fixed 20-bps threshold).
        PricingGap.objects.filter(pk=latest_gap.pk).update(
            predicted_spread_bps=round(predicted, 2),
            gap_bps=round(gap, 2),
            is_mispriced=is_mispriced,
        )
        logger.info(
            "analyse bond %s: actual=%.1f predicted=%.1f gap=%.1f bps "
            "sigma=%.2f mispriced=%s",
            bond.bond_id, actual, predicted, gap, sigma_distance, is_mispriced,
        )

        # ── f. Interpretation string ──────────────────────────────────────────
        direction = "underpriced" if gap > 0 else "overpriced"
        interpretation = (
            f"{direction} by {abs(gap):.1f} bps "
            f"({'mispriced' if is_mispriced else 'fairly priced'} — "
            f"{sigma_distance:.2f} sigma from mean)"
        )

        return {
            "bond_id": bond.bond_id,
            "bond_pk": bond.pk,
            "issuer": bond.issuer_name,
            "actual": round(actual, 2),
            "predicted": round(predicted, 2),
            "gap": round(gap, 2),
            "gap_pct": round(gap_pct, 1),
            "is_mispriced": is_mispriced,
            "interpretation": interpretation,
            "sigma": round(sigma_distance, 2),
            "r2_model": round(self.r2_test, 4),
        }

    # ── Market summary ────────────────────────────────────────────────────────

    def get_market_summary(self) -> dict:
        """
        Return aggregate cross-sectional statistics across all bonds.

        Returns:
            {
              "n_total": int,
              "n_underpriced": int,         # gap > 0 (actual > fair value)
              "n_overpriced": int,           # gap < 0
              "n_fairly_priced": int,
              "pct_underpricing_risk": float,
              "pct_overpricing_risk": float,
              "mean_gap_bps": float,
              "std_gap_bps": float,
              "mean_gap_by_category": dict,  # {category: mean_gap}
              "top5_mispriced": list[dict],  # [{bond_id, issuer, gap, sigma}]
              "r2_model": float,
            }
        """
        from pricing_analysis.models import PricingGap
        from django.db.models import Avg

        # Get all gaps, latest first per bond; deduplicate in Python
        qs = (
            PricingGap.objects
            .select_related("bond")
            .order_by("bond_id", "-checked_at")
            .values(
                "bond_id",
                "bond__bond_id",
                "bond__issuer_name",
                "bond__project_category",
                "gap_bps",
                "is_mispriced",
            )
        )
        rows = list(qs)

        if not rows:
            return {
                "n_total": 0,
                "n_underpriced": 0,
                "n_overpriced": 0,
                "n_fairly_priced": 0,
                "pct_underpricing_risk": 0.0,
                "pct_overpricing_risk": 0.0,
                "mean_gap_bps": 0.0,
                "std_gap_bps": 0.0,
                "mean_gap_by_category": {},
                "top5_mispriced": [],
                "r2_model": round(self.r2_test, 4),
            }

        df = pd.DataFrame(rows).rename(columns={
            "bond_id": "bond_pk",
            "bond__bond_id": "bond_id",
            "bond__issuer_name": "issuer",
            "bond__project_category": "category",
        })
        # Deduplicate — keep latest per bond
        df = df.drop_duplicates(subset=["bond_pk"], keep="first")
        df["gap_bps"] = df["gap_bps"].astype(float)

        n_total = len(df)
        n_under = int((df["gap_bps"] > 0).sum())   # actual > fair → underpriced
        n_over = int((df["gap_bps"] < 0).sum())
        n_fair = n_total - n_under - n_over

        mean_gap = float(df["gap_bps"].mean())
        std_gap = float(df["gap_bps"].std()) if n_total > 1 else 0.0

        # Mean gap by category
        mean_by_cat = (
            df.groupby("category")["gap_bps"]
            .mean()
            .round(1)
            .to_dict()
        )

        # Top 5 most mispriced (by |gap|)
        df["abs_gap"] = df["gap_bps"].abs()
        df["sigma_dist"] = (
            (df["gap_bps"] - self.gap_mean).abs() / max(self.gap_std, 1.0)
        )
        top5 = (
            df.nlargest(5, "abs_gap")
            [["bond_id", "issuer", "gap_bps", "sigma_dist", "is_mispriced"]]
            .rename(columns={"gap_bps": "gap", "sigma_dist": "sigma"})
            .round({"gap": 1, "sigma": 2})
            .to_dict(orient="records")
        )

        return {
            "n_total": n_total,
            "n_underpriced": n_under,
            "n_overpriced": n_over,
            "n_fairly_priced": n_fair,
            "pct_underpricing_risk": round(100 * n_under / max(n_total, 1), 1),
            "pct_overpricing_risk": round(100 * n_over / max(n_total, 1), 1),
            "mean_gap_bps": round(mean_gap, 2),
            "std_gap_bps": round(std_gap, 2),
            "mean_gap_by_category": mean_by_cat,
            "top5_mispriced": top5,
            "r2_model": round(self.r2_test, 4),
        }

    # ── Regression line + bands (for scatter chart) ───────────────────────────

    def regression_line(
        self,
        maturity_years: float = 7.0,
        credit_rating_numeric: float = DEFAULT_RATING_NUMERIC,
        step: int = 5,
    ) -> tuple[list[dict], float, float]:
        """
        Return the model regression line plus ±2σ bands.

        Args:
            maturity_years: fixed maturity for the line (use median of dataset)
            credit_rating_numeric: fixed rating for the line
            step: PCRS step size (default 5 → points at 0, 5, 10, …, 100)

        Returns:
            (line_points, upper_points, lower_points)
            where each is a list of {"x": pcrs, "y": spread_bps}
        """
        self._require_fitted()

        pcrs_values = list(range(0, 101, step))
        line, upper, lower = [], [], []

        for pcrs in pcrs_values:
            y = self.predict_spread(pcrs, maturity_years, credit_rating_numeric)
            line.append({"x": pcrs, "y": round(y, 1)})
            upper.append({"x": pcrs, "y": round(y + SIGMA_THRESHOLD * self.gap_std + self.gap_mean, 1)})
            lower.append({"x": pcrs, "y": round(y - SIGMA_THRESHOLD * self.gap_std + self.gap_mean, 1)})

        return line, upper, lower

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        """Persist model and scaler to disk."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "gap_mean": self.gap_mean,
            "gap_std": self.gap_std,
            "r2_train": self.r2_train,
            "r2_test": self.r2_test,
            "n_train": self._n_train,
        }
        with open(ANALYSER_MODEL_PATH, "wb") as f:
            pickle.dump(payload, f)
        logger.info("PricingGapAnalyser saved to %s", ANALYSER_MODEL_PATH)

    def _try_load(self) -> None:
        """Load model from disk if it exists."""
        if not ANALYSER_MODEL_PATH.exists():
            return
        try:
            with open(ANALYSER_MODEL_PATH, "rb") as f:
                payload = pickle.load(f)
            self.model = payload["model"]
            self.scaler = payload["scaler"]
            self.gap_mean = payload["gap_mean"]
            self.gap_std = payload["gap_std"]
            self.r2_train = payload.get("r2_train", 0.0)
            self.r2_test = payload.get("r2_test", 0.0)
            self._n_train = payload.get("n_train", 0)
            logger.info(
                "PricingGapAnalyser loaded from disk — R²_test=%.3f gap_std=%.1f",
                self.r2_test, self.gap_std,
            )
        except Exception as exc:
            logger.warning("Could not load PricingGapAnalyser: %s", exc)

    def _require_fitted(self) -> None:
        if self.model is None or self.scaler is None:
            raise RuntimeError(
                "PricingGapAnalyser model is not fitted. "
                "Call fit_from_db() or fit(df) first, "
                "or POST to /api/pricing/analyser/fit/"
            )

    def is_fitted(self) -> bool:
        return self.model is not None and self.scaler is not None
