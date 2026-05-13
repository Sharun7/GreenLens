# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/regulatory_compliance.py

Regulatory compliance report generation for SEBI (India) and ESMA (Europe).

Category 19 — Global vs India Context
"""
import logging
from typing import Dict, Any
from django.http import JsonResponse
from data_ingestion.models import GreenBond

logger = logging.getLogger(__name__)


class RegulatoryComplianceGenerator:
    """
    Generate region-specific regulatory compliance reports.
    """
    
    @staticmethod
    def generate_sebi_report(bond: GreenBond) -> Dict[str, Any]:
        """
        Generate SEBI Green Bond Framework compliant report for India bonds.
        
        SEBI Requirements:
        - State-level location disclosure acceptable
        - Self-reported + auditor certificate
        - Annual impact report
        - Climate risk disclosure (not yet mandatory, but GreenLens provides it)
        
        Args:
            bond: GreenBond instance
            
        Returns:
            Dictionary with SEBI-compliant disclosure fields
        """
        try:
            # Get latest climate hazard data
            latest_hazard = bond.hazard_data.order_by('-data_date').first()
            
            # Get latest PCRS score
            latest_score = bond.pcr_scores.order_by('-scored_at').first()
            
            report = {
                "bond_id": bond.bond_id,
                "issuer_name": bond.issuer_name,
                "project_category": bond.get_project_category_display(),
                "state": bond.country if bond.country == "India" else "N/A",
                "location_precision": bond.location_confidence,
                "climate_risk_score": latest_score.score if latest_score else None,
                "auditor_verified": bond.disclosure_quality in ["HIGH", "MEDIUM"],
                
                # India-specific climate risks
                "monsoon_risk": latest_hazard.monsoon_risk_index if latest_hazard and latest_hazard.monsoon_risk_index else None,
                "cyclone_risk": latest_hazard.cyclone_risk_index if latest_hazard and latest_hazard.cyclone_risk_index else None,
                "heat_wave_risk": latest_hazard.heat_wave_risk_index if latest_hazard and latest_hazard.heat_wave_risk_index else None,
                
                # Standard climate hazards
                "flood_risk": latest_hazard.flood_risk_index if latest_hazard else None,
                "heat_stress": latest_hazard.heat_stress_index if latest_hazard else None,
                "drought_spei": latest_hazard.drought_spei if latest_hazard else None,
                
                # Regulatory framework
                "regulatory_framework": bond.get_regulatory_framework_display(),
                "disclosure_quality": bond.get_disclosure_quality_display(),
                
                # Precision warning
                "precision_warning": (
                    "Location data is state-level only. Climate risk scores represent regional averages."
                    if bond.location_confidence == "country" or bond.location_confidence == "city"
                    else None
                ),
                
                # Metadata
                "report_generated_at": None,  # Will be set by view
                "data_source": bond.data_source,
            }
            
            logger.info(f"SEBI report generated for bond {bond.bond_id}")
            return report
            
        except Exception as e:
            logger.error(f"Error generating SEBI report for bond {bond.bond_id}: {e}")
            raise
    
    @staticmethod
    def generate_esma_report(bond: GreenBond) -> Dict[str, Any]:
        """
        Generate ESMA/EU Green Bond Standard compliant report for Germany bonds.
        
        EU GBS Requirements:
        - GPS-level location disclosure mandatory
        - External reviewer verification mandatory
        - EU Taxonomy alignment required
        - SFDR Article 8/9 classification
        - Principal Adverse Impacts (PAIs) disclosure
        
        Args:
            bond: GreenBond instance
            
        Returns:
            Dictionary with ESMA-compliant disclosure fields
        """
        try:
            # Get latest climate hazard data
            latest_hazard = bond.hazard_data.order_by('-data_date').first()
            
            # Get latest PCRS score
            latest_score = bond.pcr_scores.order_by('-scored_at').first()
            
            report = {
                "bond_id": bond.bond_id,
                "issuer_name": bond.issuer_name,
                "project_category": bond.get_project_category_display(),
                
                # GPS coordinates (mandatory for EU GBS)
                "gps_coordinates": {
                    "latitude": bond.lat,
                    "longitude": bond.lon,
                    "precision": bond.location_confidence,
                },
                
                # Climate risk scores
                "climate_risk_score": latest_score.score if latest_score else None,
                "accuracy_level": "high_precision" if bond.location_confidence == "precise" else "medium_precision",
                
                # EU Taxonomy alignment (placeholder - would come from bond metadata)
                "eu_taxonomy_aligned": True,  # TODO: Add field to GreenBond model
                
                # SFDR classification (placeholder - would come from bond metadata)
                "sfdr_classification": "Article_9",  # TODO: Add field to GreenBond model
                
                # External reviewer (placeholder - would come from bond metadata)
                "external_reviewer": "Verified",  # TODO: Add field to GreenBond model
                
                # Standard climate hazards
                "flood_risk": latest_hazard.flood_risk_index if latest_hazard else None,
                "heat_stress": latest_hazard.heat_stress_index if latest_hazard else None,
                "drought_spei": latest_hazard.drought_spei if latest_hazard else None,
                
                # SFDR Principal Adverse Impacts (PAIs)
                "principal_adverse_impacts": {
                    "ghg_emissions_exposure": latest_hazard.carbon_intensity_score if latest_hazard else None,
                    "carbon_footprint": latest_score.score if latest_score else None,  # Proxy via PCRS
                    "fossil_fuel_exposure": 0.0,  # Green bonds should have zero
                    "biodiversity_impact": 1.0 - latest_hazard.drought_spei if latest_hazard and latest_hazard.drought_spei else None,  # NDVI proxy
                    "water_stress": latest_hazard.drought_spei if latest_hazard else None,
                },
                
                # Regulatory framework
                "regulatory_framework": bond.get_regulatory_framework_display(),
                "disclosure_quality": bond.get_disclosure_quality_display(),
                
                # Metadata
                "report_generated_at": None,  # Will be set by view
                "data_source": bond.data_source,
            }
            
            logger.info(f"ESMA report generated for bond {bond.bond_id}")
            return report
            
        except Exception as e:
            logger.error(f"Error generating ESMA report for bond {bond.bond_id}: {e}")
            raise
    
    @staticmethod
    def get_compliance_report(bond: GreenBond) -> Dict[str, Any]:
        """
        Auto-detect region and generate appropriate compliance report.
        
        Args:
            bond: GreenBond instance
            
        Returns:
            Region-appropriate compliance report
        """
        if bond.country == "India":
            return RegulatoryComplianceGenerator.generate_sebi_report(bond)
        elif bond.country in ["Germany", "France", "Netherlands", "Spain", "Italy"]:
            return RegulatoryComplianceGenerator.generate_esma_report(bond)
        else:
            # Default to ICMA Green Bond Principles format
            logger.info(f"Using default ICMA format for bond {bond.bond_id} from {bond.country}")
            return RegulatoryComplianceGenerator.generate_sebi_report(bond)  # Use SEBI format as default
