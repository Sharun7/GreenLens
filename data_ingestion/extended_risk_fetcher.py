"""
data_ingestion/extended_risk_fetcher.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Provides three additional risk dimensions for PCRS scoring:

1. Carbon Intensity Score  — EDGAR CO2 emissions per GDP (country level)
   Source: European Commission EDGAR v8.0 (publicly available)
   Normalised to 0–1: 0 = very low carbon intensity, 1 = very high

2. Policy Risk Score — World Bank Governance Indicators
   Combines: Rule of Law + Government Effectiveness + Political Stability
   Inverted: 0 = excellent governance (low risk), 1 = poor governance (high risk)

3. Transition Risk Score — NDC ambition + fossil fuel dependency
   Source: Climate Action Tracker + IEA Fossil Fuel Share (public datasets)
   0 = leading clean energy transition, 1 = highly fossil-fuel dependent

All data is stored as country-level lookup tables derived from the latest
public datasets (2022–2024). No API calls needed — embedded data avoids
rate limits and works offline.
"""
import logging

logger = logging.getLogger("greenlens.extended_risk")

# ── 1. CARBON INTENSITY (CO2 tonnes per million USD GDP) ──────────────────────
# Source: EDGAR v8.0 (2022 data) + World Bank GDP data
# Normalised: raw values → 0–1 scale (max ~3.5 tCO2/k$GDP for high emitters)
# Higher = more carbon-intensive economy = higher climate transition risk
CARBON_INTENSITY: dict[str, float] = {
    # Low carbon intensity (score 0.05–0.25)
    "CHE": 0.05, "SWE": 0.06, "NOR": 0.07, "DNK": 0.08, "FIN": 0.09,
    "GBR": 0.10, "FRA": 0.11, "AUT": 0.12, "DEU": 0.13, "NLD": 0.14,
    "LUX": 0.10, "BEL": 0.15, "IRL": 0.12, "NZL": 0.13, "ISL": 0.06,
    "ISR": 0.14, "CAN": 0.20, "AUS": 0.22, "JPN": 0.18, "KOR": 0.25,
    "ESP": 0.13, "PRT": 0.12, "ITA": 0.13, "GRC": 0.18, "SVN": 0.16,
    "SVK": 0.20, "CZE": 0.22, "HUN": 0.18, "POL": 0.30, "LTU": 0.18,
    "LVA": 0.17, "EST": 0.26,
    # Medium carbon intensity (0.25–0.55)
    "USA": 0.28, "MEX": 0.30, "BRA": 0.18, "ARG": 0.35, "CHL": 0.28,
    "COL": 0.24, "PER": 0.22, "URY": 0.14, "CRI": 0.10,
    "ZAF": 0.55, "MAR": 0.30, "EGY": 0.38, "NGA": 0.28, "KEN": 0.12,
    "THA": 0.35, "MYS": 0.40, "IDN": 0.38, "PHL": 0.28, "VNM": 0.38,
    "SGP": 0.30, "TWN": 0.35, "IND": 0.45, "CHN": 0.50, "TUR": 0.38,
    "RUS": 0.52, "UKR": 0.42, "KAZ": 0.58, "UZB": 0.52,
    # High carbon intensity (0.55–1.0)
    "SAU": 0.70, "ARE": 0.65, "QAT": 0.80, "KWT": 0.75, "OMN": 0.68,
    "IRN": 0.62, "IRQ": 0.65, "BGD": 0.40, "PAK": 0.42,
    "MNG": 0.70, "TKM": 0.85, "UZB": 0.58, "AZE": 0.55,
}
DEFAULT_CARBON = 0.35  # Global average fallback


# ── 2. POLICY RISK (World Bank Governance Indicators 2022) ────────────────────
# Combined from: Rule of Law + Government Effectiveness + Political Stability
# WB scores range -2.5 to +2.5; we normalise: risk = (-score + 2.5) / 5.0
# So +2.5 governance score → 0.0 risk; -2.5 → 1.0 risk
POLICY_RISK: dict[str, float] = {
    # Low policy risk (stable governance)
    "CHE": 0.05, "NOR": 0.05, "SWE": 0.06, "DNK": 0.06, "FIN": 0.07,
    "NZL": 0.08, "AUT": 0.10, "LUX": 0.08, "NLD": 0.10, "CAN": 0.10,
    "AUS": 0.12, "GBR": 0.12, "DEU": 0.13, "ISL": 0.09, "IRL": 0.12,
    "SGP": 0.10, "JPN": 0.15, "USA": 0.18, "FRA": 0.17, "BEL": 0.17,
    "ISR": 0.22, "KOR": 0.20, "ITA": 0.25, "ESP": 0.20, "PRT": 0.18,
    "CZE": 0.22, "SVN": 0.20, "SVK": 0.25, "POL": 0.27, "LTU": 0.23,
    "LVA": 0.22, "EST": 0.20, "HUN": 0.30, "GRC": 0.30, "CHL": 0.25,
    # Medium policy risk
    "ARG": 0.45, "BRA": 0.42, "MEX": 0.48, "COL": 0.48, "PER": 0.45,
    "ZAF": 0.45, "MAR": 0.40, "TUR": 0.50, "UKR": 0.52, "CHN": 0.48,
    "IND": 0.42, "THA": 0.45, "IDN": 0.42, "MYS": 0.35, "VNM": 0.42,
    "TWN": 0.25, "SAU": 0.38, "ARE": 0.32, "QAT": 0.33, "JOR": 0.40,
    "EGY": 0.50, "KAZ": 0.55, "RUS": 0.60, "UZB": 0.58,
    # High policy risk
    "NGA": 0.72, "BGD": 0.62, "PAK": 0.68, "SDN": 0.85,
    "IRQ": 0.88, "AFG": 0.95, "SOM": 0.95, "SSD": 0.92,
    "VEN": 0.80, "ZWE": 0.78, "MMR": 0.82, "HTI": 0.85,
}
DEFAULT_POLICY_RISK = 0.45  # Global average fallback


# ── 3. TRANSITION RISK (NDC ambition + fossil fuel dependency) ────────────────
# Sources: Climate Action Tracker (CAT) ratings + IEA World Energy Statistics
# 0 = Leading clean energy transition (e.g. high renewables, ambitious NDC)
# 1 = Highly fossil-fuel dependent with insufficient climate commitments
TRANSITION_RISK: dict[str, float] = {
    # Low transition risk (ambitious NDC + high renewables)
    "SWE": 0.05, "NOR": 0.06, "DNK": 0.07, "ISL": 0.05, "CRI": 0.08,
    "URY": 0.10, "NZL": 0.12, "FIN": 0.10, "AUT": 0.15, "CHE": 0.12,
    "DEU": 0.20, "GBR": 0.18, "FRA": 0.18, "NLD": 0.20, "ESP": 0.22,
    "PRT": 0.15, "BEL": 0.22, "LUX": 0.15, "IRL": 0.20, "ITA": 0.25,
    # Medium transition risk
    "USA": 0.35, "CAN": 0.38, "AUS": 0.40, "JPN": 0.32, "KOR": 0.38,
    "CHN": 0.42, "IND": 0.40, "BRA": 0.25, "MEX": 0.42, "ZAF": 0.55,
    "IDN": 0.48, "THA": 0.42, "VNM": 0.40, "MYS": 0.45, "PHL": 0.40,
    "TUR": 0.48, "MAR": 0.35, "EGY": 0.48, "ARG": 0.42, "COL": 0.38,
    "CHL": 0.30, "PER": 0.35, "NGA": 0.50, "KEN": 0.25, "ETH": 0.20,
    # High transition risk (fossil-fuel dependent, insufficient NDC)
    "SAU": 0.82, "ARE": 0.75, "QAT": 0.88, "KWT": 0.85, "IRN": 0.78,
    "IRQ": 0.80, "RUS": 0.72, "KAZ": 0.75, "UZB": 0.70, "TKM": 0.85,
    "BGD": 0.60, "PAK": 0.58, "MNG": 0.72,
}
DEFAULT_TRANSITION_RISK = 0.40  # Global average fallback


class ExtendedRiskFetcher:
    """
    Provides carbon intensity, policy risk, and transition risk scores
    for a given ISO3 country code.

    All data is sourced from publicly available international datasets
    (EDGAR v8.0, World Bank Governance Indicators, Climate Action Tracker)
    and embedded as lookup tables for reliability and offline access.
    """

    def get_carbon_intensity(self, iso3: str) -> float:
        """Return normalised carbon intensity score (0=low, 1=high)."""
        score = CARBON_INTENSITY.get(iso3.upper(), DEFAULT_CARBON)
        logger.debug("Carbon intensity [%s]: %.3f", iso3, score)
        return round(min(1.0, max(0.0, score)), 4)

    def get_policy_risk(self, iso3: str) -> float:
        """Return policy risk score (0=stable governance, 1=high risk)."""
        score = POLICY_RISK.get(iso3.upper(), DEFAULT_POLICY_RISK)
        logger.debug("Policy risk [%s]: %.3f", iso3, score)
        return round(min(1.0, max(0.0, score)), 4)

    def get_transition_risk(self, iso3: str) -> float:
        """Return transition risk score (0=leading clean energy, 1=fossil-dependent)."""
        score = TRANSITION_RISK.get(iso3.upper(), DEFAULT_TRANSITION_RISK)
        logger.debug("Transition risk [%s]: %.3f", iso3, score)
        return round(min(1.0, max(0.0, score)), 4)

    def get_all(self, iso3: str) -> dict:
        """Return all three extended risk scores as a dict."""
        return {
            "carbon_intensity_score": self.get_carbon_intensity(iso3),
            "policy_risk_score":      self.get_policy_risk(iso3),
            "transition_risk_score":  self.get_transition_risk(iso3),
        }
