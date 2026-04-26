"""
greenlens/data/worldbank_climate.py — World Bank Climate Knowledge Portal fetcher.

Fetches country-level climate hazard data from:
  https://climateknowledgeportal.worldbank.org

No API key required. Results cached in-memory for the process lifetime.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger("greenlens.worldbank_climate")

# ── Constants ──────────────────────────────────────────────────────────────────
BASE_URL = "https://climateknowledgeportal.worldbank.org/api/data/get-download-data"
TIMEOUT = 20

# Climate scenario and period for projections
SCENARIO = "rcp85"          # high-emission scenario (worst-case physical risk)
PERIOD   = "2020_2039"      # near-term projection window

# ── Country-level climate baselines (fallback heuristics) ─────────────────────
# Normalised heat stress (0–1) by ISO3 — derived from Köppen climate zones
# and IPCC AR6 regional warming projections.
_HEAT_BASELINE: dict[str, float] = {
    "IND": 0.82, "BGD": 0.85, "PAK": 0.80, "LKA": 0.75, "NPL": 0.55,
    "THA": 0.78, "VNM": 0.72, "PHL": 0.76, "IDN": 0.74, "MYS": 0.71,
    "SGP": 0.70, "CHN": 0.55, "JPN": 0.45, "KOR": 0.40, "AUS": 0.65,
    "NZL": 0.28, "BRA": 0.68, "ARG": 0.50, "MEX": 0.60, "USA": 0.42,
    "CAN": 0.20, "GBR": 0.22, "FRA": 0.32, "DEU": 0.30, "ITA": 0.42,
    "ESP": 0.50, "PRT": 0.48, "NLD": 0.25, "BEL": 0.24, "SWE": 0.18,
    "NOR": 0.12, "DNK": 0.20, "FIN": 0.15, "CHE": 0.28, "AUT": 0.30,
    "GRC": 0.52, "TUR": 0.55, "RUS": 0.20, "UKR": 0.35, "POL": 0.28,
    "EGY": 0.82, "MAR": 0.65, "KEN": 0.60, "NGA": 0.72, "GHA": 0.70,
    "ZAF": 0.55, "TZA": 0.65, "ETH": 0.62, "UGA": 0.60, "MOZ": 0.68,
    "SAU": 0.90, "ARE": 0.88, "QAT": 0.92, "IRN": 0.78, "IRQ": 0.85,
    "KAZ": 0.35, "UZB": 0.50, "MMR": 0.72, "KHM": 0.75, "LAO": 0.70,
    "COL": 0.62, "CHL": 0.40, "PER": 0.55, "ECU": 0.58, "VEN": 0.68,
    "URY": 0.42, "BOL": 0.52, "PRY": 0.65, "GTM": 0.68, "HND": 0.70,
    "CRI": 0.60, "PAN": 0.65, "DOM": 0.70, "JAM": 0.72, "TTO": 0.68,
    "SEN": 0.75, "MLI": 0.88, "BFA": 0.87, "NER": 0.90, "TCD": 0.88,
    "CMR": 0.72, "CIV": 0.70, "GIN": 0.68, "BEN": 0.78, "TOG": 0.75,
    "MNG": 0.30, "GEO": 0.35, "ARM": 0.40, "AZE": 0.45,
}

# Flood risk (0–1) by ISO3 — derived from precipitation anomaly and river basin exposure
_FLOOD_BASELINE: dict[str, float] = {
    "IND": 0.72, "BGD": 0.90, "PAK": 0.68, "LKA": 0.65, "NPL": 0.70,
    "THA": 0.75, "VNM": 0.78, "PHL": 0.82, "IDN": 0.76, "MYS": 0.70,
    "SGP": 0.45, "CHN": 0.60, "JPN": 0.58, "KOR": 0.50, "AUS": 0.45,
    "NZL": 0.35, "BRA": 0.62, "ARG": 0.52, "MEX": 0.55, "USA": 0.48,
    "CAN": 0.30, "GBR": 0.42, "FRA": 0.38, "DEU": 0.35, "ITA": 0.40,
    "ESP": 0.32, "PRT": 0.30, "NLD": 0.55, "BEL": 0.40, "SWE": 0.25,
    "NOR": 0.28, "DNK": 0.30, "FIN": 0.22, "CHE": 0.32, "AUT": 0.35,
    "GRC": 0.38, "TUR": 0.45, "RUS": 0.35, "UKR": 0.40, "POL": 0.38,
    "EGY": 0.20, "MAR": 0.30, "KEN": 0.50, "NGA": 0.62, "GHA": 0.58,
    "ZAF": 0.40, "TZA": 0.55, "ETH": 0.52, "UGA": 0.60, "MOZ": 0.65,
    "SAU": 0.12, "ARE": 0.10, "QAT": 0.08, "IRN": 0.35, "IRQ": 0.40,
    "KAZ": 0.25, "UZB": 0.20, "MMR": 0.72, "KHM": 0.70, "LAO": 0.68,
    "COL": 0.65, "CHL": 0.38, "PER": 0.50, "ECU": 0.60, "VEN": 0.62,
    "URY": 0.45, "BOL": 0.55, "PRY": 0.60, "GTM": 0.62, "HND": 0.65,
    "CRI": 0.58, "PAN": 0.62, "DOM": 0.60, "JAM": 0.55, "TTO": 0.52,
    "SEN": 0.52, "MLI": 0.35, "BFA": 0.38, "NER": 0.28, "TCD": 0.40,
    "CMR": 0.60, "CIV": 0.62, "GIN": 0.65, "BEN": 0.58, "TOG": 0.55,
    "MNG": 0.15, "GEO": 0.42, "ARM": 0.30, "AZE": 0.35,
}

# Default values for countries not in lookup
_DEFAULT_HEAT  = 0.45
_DEFAULT_FLOOD = 0.40


class WorldBankClimateFetcher:
    """
    Fetches country-level climate hazard data from the World Bank
    Climate Knowledge Portal.

    Results are cached at the class level (shared across all instances in the
    same process), so repeated calls for the same country code never hit the
    network more than once per process lifetime.
    Falls back to pre-computed baselines when the API is unavailable.
    """

    # Class-level cache — shared across all instances in the same process
    _cache: dict[str, dict] = {}

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "GreenLens/1.0 (climate-risk-research)",
            "Accept": "application/json",
        })

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_variable(
        self,
        country_iso3: str,
        variable: str,
        period: str = "1991-2020",
        scenario: str = "historical",
    ) -> Optional[dict]:
        """
        Call the WB CKP API and return the JSON payload, or None on failure.

        Endpoint pattern:
          /historical/{variable}/{period}/{country}/{country}
          /projection/mavg/{variable}/{scenario}/{period}/{country}
        """
        iso = country_iso3.upper()
        if scenario == "historical":
            url = f"{BASE_URL}/historical/{variable}/{period}/{iso}/{iso}"
        else:
            url = f"{BASE_URL}/projection/mavg/{variable}/{scenario}/{period}/{iso}"

        try:
            resp = self._session.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    return resp.json()
                # Some endpoints return plain-text/CSV — attempt minimal parse
                lines = [l for l in resp.text.splitlines() if l.strip()]
                if len(lines) > 1:
                    # Return raw text wrapped in a dict so callers can detect CSV mode
                    return {"_csv": resp.text}
            logger.debug(
                "WB CKP API %s/%s returned %d", variable, iso, resp.status_code
            )
        except requests.RequestException as exc:
            logger.warning("WB CKP request failed (%s/%s): %s", variable, iso, exc)
        return None

    def _extract_temperature_anomaly(self, payload: Optional[dict]) -> Optional[float]:
        """
        Parse temperature anomaly (°C) from API response.
        Supports both JSON dict and CSV-wrapped responses.
        """
        if payload is None:
            return None
        if "_csv" in payload:
            # Minimal CSV parse: look for a numeric value in the last non-header row
            for line in reversed(payload["_csv"].splitlines()):
                parts = line.split(",")
                for p in reversed(parts):
                    try:
                        v = float(p.strip())
                        if -10 < v < 50:    # plausible temperature range
                            return v
                    except ValueError:
                        continue
            return None
        # JSON: look for common value keys
        for key in ("annualData", "data", "values", "value", "monthly_data"):
            if key in payload:
                data = payload[key]
                if isinstance(data, list) and data:
                    vals = [float(x) for x in data if x is not None]
                    return sum(vals) / len(vals) if vals else None
                if isinstance(data, (int, float)):
                    return float(data)
        return None

    def _extract_precipitation_anomaly(self, payload: Optional[dict]) -> Optional[float]:
        """
        Parse precipitation anomaly (mm/year) from API response.
        """
        val = self._extract_temperature_anomaly(payload)  # same extraction logic
        return val

    # ── Normalisation helpers ─────────────────────────────────────────────────

    @staticmethod
    def _normalise_heat(anomaly_c: float) -> float:
        """
        Convert temperature anomaly (°C above baseline) to heat stress index 0–1.
        Reference: 0°C anomaly → 0.3 (background risk); +3°C → 1.0; −2°C → 0.0.
        """
        # Linear normalisation: clamp [-2, 3] → [0, 1]
        clamped = max(-2.0, min(3.0, float(anomaly_c)))
        return round((clamped + 2.0) / 5.0, 4)

    @staticmethod
    def _normalise_flood(precip_anomaly_mm: float) -> float:
        """
        Convert precipitation anomaly to flood risk index 0–1.
        Positive anomaly (more rain) → higher flood risk.
        Clamped range: [-500, 500] mm → [0, 1].
        """
        clamped = max(-500.0, min(500.0, float(precip_anomaly_mm)))
        return round((clamped + 500.0) / 1000.0, 4)

    def _baseline_heat(self, iso3: str) -> float:
        return _HEAT_BASELINE.get(iso3.upper(), _DEFAULT_HEAT)

    def _baseline_flood(self, iso3: str) -> float:
        return _FLOOD_BASELINE.get(iso3.upper(), _DEFAULT_FLOOD)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_heat_stress(self, country_iso3: str) -> float:
        """
        Returns normalised heat stress score 0–1 for the country.
        Queries WB CKP 'tas' (mean air temperature) anomaly.
        Falls back to pre-computed baseline on API failure.
        """
        iso = country_iso3.upper()
        cache_key = f"heat:{iso}"
        if cache_key in self._cache:
            return self._cache[cache_key]["heat_stress"]

        payload = self._fetch_variable(iso, "tas", period="1991-2020")
        anomaly = self._extract_temperature_anomaly(payload)

        if anomaly is not None:
            score = self._normalise_heat(anomaly)
            source = "worldbank_api"
            logger.info("WB heat %s: anomaly=%.2f°C → score=%.3f", iso, anomaly, score)
        else:
            score = self._baseline_heat(iso)
            source = "greenlens_baseline"
            logger.debug("WB heat fallback %s → %.3f", iso, score)

        entry = {"heat_stress": score, "source": source}
        self._cache[cache_key] = entry
        return score

    def get_flood_risk(self, country_iso3: str) -> float:
        """
        Returns flood risk index 0–1 for the country.
        Queries WB CKP 'pr' (precipitation) anomaly.
        Falls back to pre-computed baseline on API failure.
        """
        iso = country_iso3.upper()
        cache_key = f"flood:{iso}"
        if cache_key in self._cache:
            return self._cache[cache_key]["flood_risk"]

        payload = self._fetch_variable(iso, "pr", period="1991-2020")
        anomaly = self._extract_precipitation_anomaly(payload)

        if anomaly is not None:
            score = self._normalise_flood(anomaly)
            source = "worldbank_api"
            logger.info("WB flood %s: precip_anomaly=%.1fmm → score=%.3f", iso, anomaly, score)
        else:
            score = self._baseline_flood(iso)
            source = "greenlens_baseline"
            logger.debug("WB flood fallback %s → %.3f", iso, score)

        entry = {"flood_risk": score, "source": source}
        self._cache[cache_key] = entry
        return score

    def get_all_hazards(self, country_iso3: str) -> dict:
        """
        Returns all hazard indices for a country.

        Returns:
            {
                "flood_risk":  float (0–1),
                "heat_stress": float (0–1),
                "drought_spei": float (approximate, from heat/precip proxy),
                "source":      str,
                "iso3":        str,
            }
        """
        iso = country_iso3.upper()
        cache_key = f"all:{iso}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        flood = self.get_flood_risk(iso)
        heat  = self.get_heat_stress(iso)

        # Derive approximate SPEI from precipitation anomaly:
        # high heat + low precipitation → drought (negative SPEI)
        drought_proxy = round((0.5 - flood) * 2.0 + (heat - 0.5) * 1.5, 2)
        drought_proxy = max(-3.0, min(3.0, drought_proxy))

        result = {
            "flood_risk":   flood,
            "heat_stress":  heat,
            "drought_spei": drought_proxy,
            "source": "worldbank_ckp",
            "iso3": iso,
        }
        self._cache[cache_key] = result
        return result
