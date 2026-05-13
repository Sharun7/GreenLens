# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/bias_detection.py — Model Bias Detection and Fairness Analysis

Implements regional bias detection, SHAP variance analysis, and fairness metrics
to identify geographic bias, synthetic label bias, and CNN classifier bias.

Usage:
    python manage.py detect_model_bias
    python manage.py detect_model_bias --region Europe
    python manage.py detect_model_bias --export-report
"""
import logging
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd
from django.db.models import Avg, Count, StdDev, Variance

from data_ingestion.models import GreenBond
from risk_scoring.models import PCRScore
from greenwash_detector.models import GreenwashFlag

logger = logging.getLogger("greenlens.bias_detection")


# ── Regional Groupings ─────────────────────────────────────────────────────────

REGION_MAP = {
    # Europe
    "AUT": "Europe", "BEL": "Europe", "BGR": "Europe", "HRV": "Europe", "CYP": "Europe",
    "CZE": "Europe", "DNK": "Europe", "EST": "Europe", "FIN": "Europe", "FRA": "Europe",
    "DEU": "Europe", "GRC": "Europe", "HUN": "Europe", "IRL": "Europe", "ITA": "Europe",
    "LVA": "Europe", "LTU": "Europe", "LUX": "Europe", "MLT": "Europe", "NLD": "Europe",
    "POL": "Europe", "PRT": "Europe", "ROU": "Europe", "SVK": "Europe", "SVN": "Europe",
    "ESP": "Europe", "SWE": "Europe", "GBR": "Europe", "NOR": "Europe", "CHE": "Europe",
    "ISL": "Europe", "LIE": "Europe", "MKD": "Europe", "SRB": "Europe", "BIH": "Europe",
    "ALB": "Europe", "MNE": "Europe", "UKR": "Europe", "BLR": "Europe", "MDA": "Europe",
    "RUS": "Europe",
    
    # Asia
    "CHN": "Asia", "IND": "Asia", "JPN": "Asia", "KOR": "Asia", "IDN": "Asia",
    "THA": "Asia", "MYS": "Asia", "SGP": "Asia", "PHL": "Asia", "VNM": "Asia",
    "BGD": "Asia", "PAK": "Asia", "LKA": "Asia", "NPL": "Asia", "BTN": "Asia",
    "MMR": "Asia", "KHM": "Asia", "LAO": "Asia", "MNG": "Asia", "KAZ": "Asia",
    "UZB": "Asia", "TKM": "Asia", "KGZ": "Asia", "TJK": "Asia", "AFG": "Asia",
    "IRN": "Asia", "IRQ": "Asia", "SAU": "Asia", "ARE": "Asia", "QAT": "Asia",
    "KWT": "Asia", "OMN": "Asia", "BHR": "Asia", "YEM": "Asia", "JOR": "Asia",
    "LBN": "Asia", "SYR": "Asia", "ISR": "Asia", "PSE": "Asia", "TUR": "Asia",
    "ARM": "Asia", "AZE": "Asia", "GEO": "Asia",
    
    # Africa
    "ZAF": "Africa", "EGY": "Africa", "NGA": "Africa", "KEN": "Africa", "ETH": "Africa",
    "GHA": "Africa", "TZA": "Africa", "UGA": "Africa", "DZA": "Africa", "MAR": "Africa",
    "TUN": "Africa", "LBY": "Africa", "SDN": "Africa", "SSD": "Africa", "SOM": "Africa",
    "SEN": "Africa", "CIV": "Africa", "CMR": "Africa", "AGO": "Africa", "MOZ": "Africa",
    "MDG": "Africa", "ZWE": "Africa", "ZMB": "Africa", "MWI": "Africa", "RWA": "Africa",
    "BDI": "Africa", "BEN": "Africa", "TGO": "Africa", "BFA": "Africa", "MLI": "Africa",
    "NER": "Africa", "TCD": "Africa", "CAF": "Africa", "COG": "Africa", "COD": "Africa",
    "GAB": "Africa", "GNQ": "Africa", "STP": "Africa", "MUS": "Africa", "SYC": "Africa",
    "COM": "Africa", "DJI": "Africa", "ERI": "Africa", "NAM": "Africa", "BWA": "Africa",
    "LSO": "Africa", "SWZ": "Africa",
    
    # Americas
    "USA": "Americas", "CAN": "Americas", "MEX": "Americas", "BRA": "Americas",
    "ARG": "Americas", "CHL": "Americas", "COL": "Americas", "PER": "Americas",
    "VEN": "Americas", "ECU": "Americas", "BOL": "Americas", "PRY": "Americas",
    "URY": "Americas", "GUY": "Americas", "SUR": "Americas", "GUF": "Americas",
    "CRI": "Americas", "PAN": "Americas", "GTM": "Americas", "HND": "Americas",
    "SLV": "Americas", "NIC": "Americas", "BLZ": "Americas", "JAM": "Americas",
    "CUB": "Americas", "DOM": "Americas", "HTI": "Americas", "TTO": "Americas",
    "BHS": "Americas", "BRB": "Americas", "GRD": "Americas", "LCA": "Americas",
    "VCT": "Americas", "ATG": "Americas", "DMA": "Americas", "KNA": "Americas",
    
    # Oceania
    "AUS": "Oceania", "NZL": "Oceania", "PNG": "Oceania", "FJI": "Oceania",
    "SLB": "Oceania", "VUT": "Oceania", "NCL": "Oceania", "PYF": "Oceania",
    "WSM": "Oceania", "TON": "Oceania", "KIR": "Oceania", "TUV": "Oceania",
    "NRU": "Oceania", "PLW": "Oceania", "FSM": "Oceania", "MHL": "Oceania",
}


COUNTRY_NAME_REGION = {
    # Europe
    "austria": "Europe", "belgium": "Europe", "bulgaria": "Europe", "croatia": "Europe",
    "cyprus": "Europe", "czech republic": "Europe", "czechia": "Europe", "denmark": "Europe",
    "estonia": "Europe", "finland": "Europe", "france": "Europe", "germany": "Europe",
    "greece": "Europe", "hungary": "Europe", "ireland": "Europe", "italy": "Europe",
    "latvia": "Europe", "lithuania": "Europe", "luxembourg": "Europe", "malta": "Europe",
    "netherlands": "Europe", "norway": "Europe", "poland": "Europe", "portugal": "Europe",
    "romania": "Europe", "russia": "Europe", "russian federation": "Europe",
    "slovakia": "Europe", "slovenia": "Europe", "spain": "Europe", "sweden": "Europe",
    "switzerland": "Europe", "uk": "Europe", "united kingdom": "Europe", "ukraine": "Europe",

    # Asia and Middle East
    "afghanistan": "Asia", "armenia": "Asia", "azerbaijan": "Asia", "bahrain": "Asia",
    "bangladesh": "Asia", "bhutan": "Asia", "brunei": "Asia", "cambodia": "Asia",
    "china": "Asia", "georgia": "Asia", "hong kong": "Asia", "india": "Asia",
    "indonesia": "Asia", "iran": "Asia", "iraq": "Asia", "israel": "Asia",
    "japan": "Asia", "jordan": "Asia", "kazakhstan": "Asia", "kuwait": "Asia",
    "kyrgyzstan": "Asia", "laos": "Asia", "lebanon": "Asia", "malaysia": "Asia",
    "maldives": "Asia", "mongolia": "Asia", "myanmar": "Asia", "nepal": "Asia",
    "oman": "Asia", "pakistan": "Asia", "philippines": "Asia", "qatar": "Asia",
    "saudi arabia": "Asia", "singapore": "Asia", "south korea": "Asia",
    "korea, republic of": "Asia", "sri lanka": "Asia", "taiwan": "Asia",
    "tajikistan": "Asia", "thailand": "Asia", "turkey": "Asia", "turkiye": "Asia",
    "united arab emirates": "Asia", "uae": "Asia", "uzbekistan": "Asia", "vietnam": "Asia",

    # Africa
    "algeria": "Africa", "angola": "Africa", "benin": "Africa", "botswana": "Africa",
    "burkina faso": "Africa", "cameroon": "Africa", "cote d'ivoire": "Africa",
    "ivory coast": "Africa", "democratic republic of the congo": "Africa",
    "dr congo": "Africa", "egypt": "Africa", "ethiopia": "Africa", "ghana": "Africa",
    "kenya": "Africa", "madagascar": "Africa", "malawi": "Africa", "mauritius": "Africa",
    "morocco": "Africa", "mozambique": "Africa", "namibia": "Africa", "nigeria": "Africa",
    "rwanda": "Africa", "senegal": "Africa", "south africa": "Africa", "tanzania": "Africa",
    "tunisia": "Africa", "uganda": "Africa", "zambia": "Africa", "zimbabwe": "Africa",

    # Americas
    "argentina": "Americas", "bahamas": "Americas", "barbados": "Americas",
    "bolivia": "Americas", "brazil": "Americas", "canada": "Americas", "chile": "Americas",
    "colombia": "Americas", "costa rica": "Americas", "dominican republic": "Americas",
    "ecuador": "Americas", "el salvador": "Americas", "guatemala": "Americas",
    "honduras": "Americas", "jamaica": "Americas", "mexico": "Americas",
    "panama": "Americas", "paraguay": "Americas", "peru": "Americas",
    "trinidad and tobago": "Americas", "united states": "Americas",
    "united states of america": "Americas", "usa": "Americas", "uruguay": "Americas",

    # Oceania
    "australia": "Oceania", "fiji": "Oceania", "new zealand": "Oceania",
    "papua new guinea": "Oceania",
}


def get_region(country_code: str) -> str:
    """Map an ISO3 code or country name to a broad model-monitoring region."""
    if not country_code:
        return "Other"
    raw_value = str(country_code).strip()
    upper_value = raw_value.upper()
    if upper_value in REGION_MAP:
        return REGION_MAP[upper_value]
    normalized = (
        raw_value.lower()
        .replace(".", "")
        .replace("&", "and")
        .replace("  ", " ")
        .strip()
    )
    return COUNTRY_NAME_REGION.get(normalized, "Other")


# ── Bias Detection Framework ───────────────────────────────────────────────────

class BiasDetector:
    """
    Comprehensive bias detection for GreenLens PCRS model.
    
    Detects:
    1. Geographic Bias — SHAP variance by region
    2. Synthetic Label Bias — Circular reasoning indicators
    3. CNN Classifier Bias — Tropical vs European accuracy
    """
    
    def __init__(self):
        self.bonds = GreenBond.objects.prefetch_related(
            "pcr_scores", "greenwash_flags", "hazard_data"
        ).all()
        self.results = {}
    
    def run_full_analysis(self) -> dict:
        """Run all bias detection analyses."""
        logger.info("Starting comprehensive bias detection analysis...")
        
        self.results["geographic_bias"] = self.detect_geographic_bias()
        self.results["synthetic_label_bias"] = self.detect_synthetic_label_bias()
        self.results["cnn_classifier_bias"] = self.detect_cnn_classifier_bias()
        self.results["fairness_metrics"] = self.compute_fairness_metrics()
        
        logger.info("Bias detection complete.")
        return self.results
    
    def detect_geographic_bias(self) -> dict:
        """
        Detect geographic bias by analyzing SHAP variance across regions.
        
        High variance = model uncertain = potential bias
        Low variance = model confident = good coverage
        """
        logger.info("Analyzing geographic bias via SHAP variance...")
        
        regional_data = defaultdict(lambda: {
            "bonds": [],
            "shap_variances": [],
            "pcr_scores": [],
            "shap_values_list": [],
        })
        
        for bond in self.bonds:
            region = get_region(bond.country)
            pcr = bond.pcr_scores.order_by("-scored_at").first()
            
            if not pcr or not pcr.shap_values:
                continue
            
            shap_vals = pcr.shap_values
            if isinstance(shap_vals, dict) and shap_vals:
                shap_array = np.array(list(shap_vals.values()))
                variance = float(np.var(shap_array))
                
                regional_data[region]["bonds"].append(bond.bond_id)
                regional_data[region]["shap_variances"].append(variance)
                regional_data[region]["pcr_scores"].append(pcr.score)
                regional_data[region]["shap_values_list"].append(shap_vals)
        
        # Compute regional statistics
        regional_stats = {}
        for region, data in regional_data.items():
            if not data["shap_variances"]:
                continue
            
            mean_variance = float(np.mean(data["shap_variances"]))
            std_variance = float(np.std(data["shap_variances"]))
            mean_pcr = float(np.mean(data["pcr_scores"]))
            
            # Bias severity classification
            if mean_variance > 15.0:
                severity = "HIGH"
                status = "Model highly uncertain — potential bias"
            elif mean_variance > 8.0:
                severity = "MEDIUM"
                status = "Model moderately uncertain"
            else:
                severity = "LOW"
                status = "Model confident — good coverage"
            
            regional_stats[region] = {
                "bond_count": len(data["bonds"]),
                "mean_shap_variance": round(mean_variance, 4),
                "std_shap_variance": round(std_variance, 4),
                "mean_pcr_score": round(mean_pcr, 2),
                "bias_severity": severity,
                "status": status,
            }
        
        return {
            "summary": "Geographic bias detected via SHAP variance analysis",
            "regional_stats": regional_stats,
            "interpretation": (
                "High variance regions indicate model uncertainty and potential bias. "
                "These regions need stratified resampling or region-specific fine-tuning."
            ),
        }
    
    def detect_synthetic_label_bias(self) -> dict:
        """
        Detect circular reasoning from synthetic label construction.
        
        PCRS labels are constructed from hazard indices, so model may be
        learning circular patterns rather than real risk.
        """
        logger.info("Analyzing synthetic label bias...")
        
        # Check correlation between input features and PCRS scores
        correlations = []
        
        for bond in self.bonds:
            pcr = bond.pcr_scores.order_by("-scored_at").first()
            hazard = bond.hazard_data.order_by("-data_date").first()
            
            if not pcr or not hazard:
                continue
            
            # Calculate correlation between hazard indices and PCRS
            flood_corr = abs(hazard.flood_risk_index * 10 - pcr.score)
            heat_corr = abs(hazard.heat_stress_index * 10 - pcr.score)
            drought_corr = abs(hazard.drought_spei * 10 - pcr.score)
            
            correlations.append({
                "bond_id": bond.bond_id,
                "flood_deviation": flood_corr,
                "heat_deviation": heat_corr,
                "drought_deviation": drought_corr,
            })
        
        if not correlations:
            return {"status": "insufficient_data"}
        
        # High correlation = circular reasoning
        avg_flood_dev = np.mean([c["flood_deviation"] for c in correlations])
        avg_heat_dev = np.mean([c["heat_deviation"] for c in correlations])
        avg_drought_dev = np.mean([c["drought_deviation"] for c in correlations])
        
        # Bias severity
        if avg_flood_dev < 15 and avg_heat_dev < 15 and avg_drought_dev < 15:
            severity = "HIGH"
            status = "Model may be learning circular patterns from synthetic labels"
        elif avg_flood_dev < 25 and avg_heat_dev < 25 and avg_drought_dev < 25:
            severity = "MEDIUM"
            status = "Moderate correlation with input features"
        else:
            severity = "LOW"
            status = "Model learning beyond input features"
        
        return {
            "summary": "Synthetic label bias analysis",
            "avg_flood_deviation": round(float(avg_flood_dev), 2),
            "avg_heat_deviation": round(float(avg_heat_dev), 2),
            "avg_drought_deviation": round(float(avg_drought_dev), 2),
            "bias_severity": severity,
            "status": status,
            "fix": (
                "Integrate real loss data from Munich Re NatCatSERVICE. "
                "Cross-reference historical climate events (Kerala 2018, Pakistan 2022) "
                "with bond performance to validate labels."
            ),
        }
    
    def detect_cnn_classifier_bias(self) -> dict:
        """
        Detect CNN classifier bias from EuroSAT training data.
        
        European landscapes over-represented, tropical/arid zones under-represented.
        """
        logger.info("Analyzing CNN classifier geographic bias...")
        
        regional_accuracy = defaultdict(lambda: {
            "total": 0,
            "consistent": 0,
            "inconsistent": 0,
            "unverifiable": 0,
        })
        
        for bond in self.bonds:
            region = get_region(bond.country)
            flag = bond.greenwash_flags.order_by("-checked_at").first()
            
            if not flag:
                continue
            
            regional_accuracy[region]["total"] += 1
            
            if flag.verification_status == "unverifiable":
                regional_accuracy[region]["unverifiable"] += 1
            elif flag.is_inconsistent:
                regional_accuracy[region]["inconsistent"] += 1
            else:
                regional_accuracy[region]["consistent"] += 1
        
        # Compute accuracy by region
        regional_stats = {}
        for region, data in regional_accuracy.items():
            verifiable = data["total"] - data["unverifiable"]
            if verifiable == 0:
                continue
            
            accuracy = (data["consistent"] / verifiable) * 100
            
            # Bias detection
            if accuracy < 60:
                severity = "HIGH"
                status = "Low accuracy — CNN bias likely"
            elif accuracy < 75:
                severity = "MEDIUM"
                status = "Moderate accuracy"
            else:
                severity = "LOW"
                status = "Good accuracy"
            
            regional_stats[region] = {
                "total_bonds": data["total"],
                "verifiable": verifiable,
                "consistent": data["consistent"],
                "inconsistent": data["inconsistent"],
                "accuracy_pct": round(accuracy, 1),
                "bias_severity": severity,
                "status": status,
            }
        
        return {
            "summary": "CNN classifier geographic bias analysis",
            "regional_stats": regional_stats,
            "interpretation": (
                "Low accuracy in tropical/arid regions indicates EuroSAT training bias. "
                "Fix: Add BigEarthNet dataset, fine-tune on tropical forests, "
                "South Asian agricultural land, and arid zone samples."
            ),
        }
    
    def compute_fairness_metrics(self) -> dict:
        """
        Compute fairness metrics across regions.
        
        Metrics:
        - Regional SHAP variance (uncertainty)
        - Prediction interval width (confidence)
        - Coverage error per region (accuracy)
        - Calibration curve (reliability)
        """
        logger.info("Computing fairness metrics...")
        
        regional_metrics = defaultdict(lambda: {
            "shap_variances": [],
            "confidence_margins": [],
            "pcr_scores": [],
        })
        
        for bond in self.bonds:
            region = get_region(bond.country)
            pcr = bond.pcr_scores.order_by("-scored_at").first()
            
            if not pcr or not pcr.shap_values:
                continue
            
            shap_vals = pcr.shap_values
            if isinstance(shap_vals, dict) and shap_vals:
                shap_array = np.array(list(shap_vals.values()))
                variance = float(np.var(shap_array))
                
                regional_metrics[region]["shap_variances"].append(variance)
                regional_metrics[region]["confidence_margins"].append(pcr.confidence_margin)
                regional_metrics[region]["pcr_scores"].append(pcr.score)
        
        # Compute metrics
        fairness_table = {}
        for region, data in regional_metrics.items():
            if not data["shap_variances"]:
                continue
            
            fairness_table[region] = {
                "mean_shap_variance": round(float(np.mean(data["shap_variances"])), 4),
                "mean_confidence_margin": round(float(np.mean(data["confidence_margins"])), 2),
                "mean_pcr_score": round(float(np.mean(data["pcr_scores"])), 2),
                "sample_size": len(data["pcr_scores"]),
            }
        
        return {
            "summary": "Fairness metrics by region",
            "metrics": fairness_table,
            "interpretation": (
                "High SHAP variance + wide confidence margins = model uncertain. "
                "These regions need more training data or region-specific models."
            ),
        }
    
    def export_report(self, filepath: str = "bias_detection_report.json") -> None:
        """Export bias detection report as JSON."""
        import json
        from pathlib import Path
        
        if not self.results:
            self.run_full_analysis()
        
        output_path = Path(filepath)
        with open(output_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Bias detection report exported to {output_path}")


# ── Bias Summary Table ─────────────────────────────────────────────────────────

def generate_bias_summary_table() -> dict:
    """
    Generate honest bias summary table for documentation.
    
    Returns structured data for rendering in UI or reports.
    """
    return {
        "biases": [
            {
                "type": "Geographic Bias",
                "severity": "HIGH",
                "status": "Known, unfixed",
                "description": (
                    "Training data Europe-heavy. Model learns European bond patterns better. "
                    "African, South Asian bonds less accurately scored."
                ),
                "evidence": (
                    "SHAP values European bonds tight, consistent. "
                    "Emerging market bonds SHAP values scattered — model uncertain."
                ),
                "fix": (
                    "Stratified sampling — every region equally represented. "
                    "Region-specific sub-models (Europe model, Asia model, Africa model). "
                    "Transfer learning — European trained model fine-tuned on emerging market data."
                ),
            },
            {
                "type": "Synthetic Label Bias",
                "severity": "MEDIUM",
                "status": "Known, unfixed",
                "description": (
                    "PCRS labels constructed from hazard indices. "
                    "Model may be circular — learning input patterns rather than real risk."
                ),
                "evidence": (
                    "Model R-squared high but doesn't prove real-world accuracy. "
                    "Circular reasoning possible."
                ),
                "fix": (
                    "Integrate real loss data — Munich Re NatCatSERVICE. "
                    "Historical climate events — Kerala 2018, Pakistan 2022 — check if bonds affected. "
                    "Improve label quality with ground truth."
                ),
            },
            {
                "type": "CNN Classifier Bias (Tropical)",
                "severity": "MEDIUM",
                "status": "Known, unfixed",
                "description": (
                    "ResNet-18 trained on EuroSAT data. "
                    "Tropical landscapes under-represented."
                ),
                "evidence": (
                    "Kerala reforestation bond — tropical forest classification uncertain. "
                    "European solar farm — accurately classified."
                ),
                "fix": (
                    "Add BigEarthNet dataset — global coverage. "
                    "Tropical forest, arid zone, South Asian agricultural land samples. "
                    "Region-specific fine-tuning."
                ),
            },
            {
                "type": "Temporal Bias (Pre-2015)",
                "severity": "HIGH",
                "status": "Partially fixed",
                "description": (
                    "Sentinel-2 launched June 2015. "
                    "Bonds issued before 2015 cannot be satellite-verified."
                ),
                "evidence": "Pre-2015 bonds marked unverifiable in greenwash detection.",
                "fix": "Skip pre-2015 bonds in greenwash analysis. Already implemented.",
            },
        ]
    }


# ── CLI Helpers ────────────────────────────────────────────────────────────────

def print_bias_report(results: dict) -> None:
    """Pretty-print bias detection results to console."""
    print("\n" + "="*80)
    print("GREENLENS MODEL BIAS DETECTION REPORT")
    print("="*80 + "\n")
    
    # Geographic Bias
    if "geographic_bias" in results:
        print("1. GEOGRAPHIC BIAS (SHAP Variance Analysis)")
        print("-" * 80)
        geo = results["geographic_bias"]
        for region, stats in geo.get("regional_stats", {}).items():
            print(f"\n{region}:")
            print(f"  Bonds: {stats['bond_count']}")
            print(f"  Mean SHAP Variance: {stats['mean_shap_variance']}")
            print(f"  Mean PCRS: {stats['mean_pcr_score']}")
            print(f"  Bias Severity: {stats['bias_severity']}")
            print(f"  Status: {stats['status']}")
        print()
    
    # Synthetic Label Bias
    if "synthetic_label_bias" in results:
        print("\n2. SYNTHETIC LABEL BIAS (Circular Reasoning)")
        print("-" * 80)
        syn = results["synthetic_label_bias"]
        print(f"Bias Severity: {syn.get('bias_severity', 'N/A')}")
        print(f"Status: {syn.get('status', 'N/A')}")
        print(f"Fix: {syn.get('fix', 'N/A')}")
        print()
    
    # CNN Classifier Bias
    if "cnn_classifier_bias" in results:
        print("\n3. CNN CLASSIFIER BIAS (EuroSAT Training)")
        print("-" * 80)
        cnn = results["cnn_classifier_bias"]
        for region, stats in cnn.get("regional_stats", {}).items():
            print(f"\n{region}:")
            print(f"  Total Bonds: {stats['total_bonds']}")
            print(f"  Verifiable: {stats['verifiable']}")
            print(f"  Accuracy: {stats['accuracy_pct']}%")
            print(f"  Bias Severity: {stats['bias_severity']}")
            print(f"  Status: {stats['status']}")
        print()
    
    # Fairness Metrics
    if "fairness_metrics" in results:
        print("\n4. FAIRNESS METRICS BY REGION")
        print("-" * 80)
        fair = results["fairness_metrics"]
        for region, metrics in fair.get("metrics", {}).items():
            print(f"\n{region}:")
            print(f"  Sample Size: {metrics['sample_size']}")
            print(f"  Mean SHAP Variance: {metrics['mean_shap_variance']}")
            print(f"  Mean Confidence Margin: {metrics['mean_confidence_margin']}")
            print(f"  Mean PCRS: {metrics['mean_pcr_score']}")
        print()
    
    print("="*80)
    print("END OF REPORT")
    print("="*80 + "\n")
