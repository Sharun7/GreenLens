# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
risk_scoring/india_climate_enhancer.py

India-specific climate data enhancement module.
Supplements World Bank data with IMD (India Meteorological Department) precision.

Category 19 — Global vs India Context
"""
import logging
import math
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from django.core.cache import cache

logger = logging.getLogger(__name__)


# State-level risk profiles for all Indian states and union territories
STATE_RISK_PROFILES = {
    # Coastal states with high monsoon + cyclone risk
    "Kerala": {
        "monsoon_base": 0.8,  # High monsoon flood risk
        "cyclone_base": 0.7,  # High cyclone risk (Arabian Sea)
        "heat_base": 0.4,     # Moderate heat risk
        "region": "coastal_southwest"
    },
    "Tamil Nadu": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.8,  # Very high cyclone risk (Bay of Bengal)
        "heat_base": 0.7,     # High heat risk
        "region": "coastal_southeast"
    },
    "Odisha": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.9,  # Extreme cyclone risk (Fani 2019, etc.)
        "heat_base": 0.6,
        "region": "coastal_east"
    },
    "West Bengal": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.7,  # High cyclone risk (Bay of Bengal)
        "heat_base": 0.5,
        "region": "coastal_east"
    },
    "Andhra Pradesh": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.7,
        "heat_base": 0.7,
        "region": "coastal_southeast"
    },
    "Gujarat": {
        "monsoon_base": 0.5,
        "cyclone_base": 0.6,  # Moderate cyclone risk (Arabian Sea)
        "heat_base": 0.8,     # Very high heat risk
        "region": "coastal_west"
    },
    "Maharashtra": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.5,
        "heat_base": 0.6,
        "region": "coastal_west"
    },
    "Goa": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.4,
        "heat_base": 0.5,
        "region": "coastal_west"
    },
    "Karnataka": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.3,  # Coastal Karnataka has some risk
        "heat_base": 0.6,
        "region": "coastal_southwest"
    },
    
    # Inland states with high heat + drought risk
    "Rajasthan": {
        "monsoon_base": 0.3,  # Low monsoon risk (desert)
        "cyclone_base": 0.0,  # Zero cyclone risk (inland)
        "heat_base": 0.9,     # Extreme heat risk (Thar Desert)
        "region": "inland_northwest"
    },
    "Madhya Pradesh": {
        "monsoon_base": 0.5,
        "cyclone_base": 0.0,
        "heat_base": 0.7,
        "region": "inland_central"
    },
    "Chhattisgarh": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.0,
        "heat_base": 0.6,
        "region": "inland_central"
    },
    "Uttar Pradesh": {
        "monsoon_base": 0.5,
        "cyclone_base": 0.0,
        "heat_base": 0.7,
        "region": "inland_north"
    },
    "Bihar": {
        "monsoon_base": 0.7,  # High flood risk from rivers
        "cyclone_base": 0.0,
        "heat_base": 0.6,
        "region": "inland_north"
    },
    "Jharkhand": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.0,
        "heat_base": 0.6,
        "region": "inland_east"
    },
    
    # Himalayan states with flash flood + landslide risk
    "Uttarakhand": {
        "monsoon_base": 0.8,  # High flash flood risk (2013 Kedarnath)
        "cyclone_base": 0.0,
        "heat_base": 0.2,     # Low heat risk (mountains)
        "region": "himalayan"
    },
    "Himachal Pradesh": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.2,
        "region": "himalayan"
    },
    "Jammu and Kashmir": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.0,
        "heat_base": 0.2,
        "region": "himalayan"
    },
    "Ladakh": {
        "monsoon_base": 0.3,  # Low monsoon impact
        "cyclone_base": 0.0,
        "heat_base": 0.1,
        "region": "himalayan"
    },
    
    # Northeast states with high monsoon risk
    "Assam": {
        "monsoon_base": 0.8,  # Very high monsoon flood risk (Brahmaputra)
        "cyclone_base": 0.0,
        "heat_base": 0.4,
        "region": "northeast"
    },
    "Meghalaya": {
        "monsoon_base": 0.9,  # Extreme monsoon (Cherrapunji)
        "cyclone_base": 0.0,
        "heat_base": 0.3,
        "region": "northeast"
    },
    "Arunachal Pradesh": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.3,
        "region": "northeast"
    },
    "Nagaland": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.3,
        "region": "northeast"
    },
    "Manipur": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.3,
        "region": "northeast"
    },
    "Mizoram": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.3,
        "region": "northeast"
    },
    "Tripura": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.4,
        "region": "northeast"
    },
    "Sikkim": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.0,
        "heat_base": 0.2,
        "region": "himalayan"
    },
    
    # Other states
    "Punjab": {
        "monsoon_base": 0.4,
        "cyclone_base": 0.0,
        "heat_base": 0.7,
        "region": "inland_northwest"
    },
    "Haryana": {
        "monsoon_base": 0.4,
        "cyclone_base": 0.0,
        "heat_base": 0.8,
        "region": "inland_northwest"
    },
    "Delhi": {
        "monsoon_base": 0.4,
        "cyclone_base": 0.0,
        "heat_base": 0.8,
        "region": "inland_northwest"
    },
    "Telangana": {
        "monsoon_base": 0.5,
        "cyclone_base": 0.0,
        "heat_base": 0.7,
        "region": "inland_south"
    },
    
    # Union Territories
    "Puducherry": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.7,
        "heat_base": 0.6,
        "region": "coastal_southeast"
    },
    "Chandigarh": {
        "monsoon_base": 0.4,
        "cyclone_base": 0.0,
        "heat_base": 0.7,
        "region": "inland_northwest"
    },
    "Andaman and Nicobar Islands": {
        "monsoon_base": 0.7,
        "cyclone_base": 0.8,  # High cyclone risk (Bay of Bengal)
        "heat_base": 0.5,
        "region": "island"
    },
    "Lakshadweep": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.6,
        "heat_base": 0.5,
        "region": "island"
    },
    "Dadra and Nagar Haveli and Daman and Diu": {
        "monsoon_base": 0.6,
        "cyclone_base": 0.4,
        "heat_base": 0.6,
        "region": "coastal_west"
    },
}


class IndiaClimateEnhancer:
    """
    India-specific climate data enhancement.
    Supplements World Bank data with IMD precision.
    """
    
    def __init__(self):
        self.imd_api_available = False  # Will be True when IMD API is integrated
        
    def get_monsoon_risk(self, lat: float, lon: float, state: Optional[str] = None) -> float:
        """
        Calculate monsoon risk score for India bonds.
        
        Args:
            lat: Latitude of project location
            lon: Longitude of project location
            state: Indian state name (optional, improves accuracy)
            
        Returns:
            Monsoon risk score (0.0 = no risk, 1.0 = extreme risk)
        """
        try:
            # Get state-level base risk
            if state and state in STATE_RISK_PROFILES:
                base_risk = STATE_RISK_PROFILES[state]["monsoon_base"]
                region = STATE_RISK_PROFILES[state]["region"]
            else:
                # Fallback: estimate from coordinates
                base_risk, region = self._estimate_monsoon_from_coords(lat, lon)
            
            # Check for cached IMD seasonal forecast
            cache_key = f"imd_monsoon_{state or f'{lat:.2f}_{lon:.2f}'}"
            imd_forecast = cache.get(cache_key)
            
            if imd_forecast is None and self.imd_api_available:
                # TODO: Integrate IMD seasonal forecast API
                # imd_forecast = self._fetch_imd_seasonal_forecast(lat, lon)
                # cache.set(cache_key, imd_forecast, timeout=86400)  # 24 hours
                pass
            
            # Get ENSO phase adjustment
            enso_adjustment = self._get_enso_adjustment()
            
            # Calculate final monsoon risk
            monsoon_risk = min(1.0, base_risk * (1.0 + enso_adjustment))
            
            logger.info(
                f"Monsoon risk calculated: {monsoon_risk:.3f} "
                f"(base={base_risk:.3f}, ENSO={enso_adjustment:+.3f}, region={region})"
            )
            
            return round(monsoon_risk, 3)
            
        except Exception as e:
            logger.error(f"Error calculating monsoon risk: {e}")
            return 0.5  # Default moderate risk
    
    def get_cyclone_risk(self, lat: float, lon: float, state: Optional[str] = None) -> float:
        """
        Calculate cyclone risk score for India coastal bonds.
        
        Args:
            lat: Latitude of project location
            lon: Longitude of project location
            state: Indian state name (optional)
            
        Returns:
            Cyclone risk score (0.0 = no risk, 1.0 = extreme risk)
        """
        try:
            # Get state-level base risk
            if state and state in STATE_RISK_PROFILES:
                base_risk = STATE_RISK_PROFILES[state]["cyclone_base"]
            else:
                # Fallback: check if coastal
                base_risk = self._estimate_cyclone_from_coords(lat, lon)
            
            # If inland state, return zero
            if base_risk == 0.0:
                return 0.0
            
            # Check for cached IMD cyclone track data
            cache_key = f"imd_cyclone_{lat:.2f}_{lon:.2f}"
            historical_distance = cache.get(cache_key)
            
            if historical_distance is None and self.imd_api_available:
                # TODO: Integrate IMD historical cyclone track data
                # historical_distance = self._fetch_imd_cyclone_distance(lat, lon)
                # cache.set(cache_key, historical_distance, timeout=86400 * 30)  # 30 days
                pass
            
            # Distance-based risk adjustment (if IMD data available)
            if historical_distance is not None:
                if historical_distance < 100:  # Within 100 km
                    distance_factor = 1.0
                elif historical_distance < 300:  # 100-300 km
                    distance_factor = 0.6
                else:  # > 300 km
                    distance_factor = 0.3
                
                cyclone_risk = base_risk * distance_factor
            else:
                cyclone_risk = base_risk
            
            logger.info(f"Cyclone risk calculated: {cyclone_risk:.3f} (base={base_risk:.3f})")
            
            return round(cyclone_risk, 3)
            
        except Exception as e:
            logger.error(f"Error calculating cyclone risk: {e}")
            return 0.3  # Default low-moderate risk
    
    def get_heat_wave_risk(self, lat: float, lon: float, state: Optional[str] = None) -> float:
        """
        Calculate heat wave risk using WBGT (Wet Bulb Globe Temperature).
        
        Args:
            lat: Latitude of project location
            lon: Longitude of project location
            state: Indian state name (optional)
            
        Returns:
            Heat wave risk score (0.0 = low, 1.0 = extreme)
        """
        try:
            # Get state-level base risk
            if state and state in STATE_RISK_PROFILES:
                base_risk = STATE_RISK_PROFILES[state]["heat_base"]
            else:
                # Fallback: estimate from coordinates
                base_risk = self._estimate_heat_from_coords(lat, lon)
            
            # Check for cached IMD heat wave frequency data
            cache_key = f"imd_heat_{state or f'{lat:.2f}_{lon:.2f}'}"
            imd_heat_data = cache.get(cache_key)
            
            if imd_heat_data is None and self.imd_api_available:
                # TODO: Integrate IMD heat wave frequency API
                # imd_heat_data = self._fetch_imd_heat_wave_frequency(lat, lon)
                # cache.set(cache_key, imd_heat_data, timeout=86400 * 7)  # 7 days
                pass
            
            # WBGT calculation would go here
            # For now, use base risk from state profiles
            heat_wave_risk = base_risk
            
            logger.info(f"Heat wave risk calculated: {heat_wave_risk:.3f} (base={base_risk:.3f})")
            
            return round(heat_wave_risk, 3)
            
        except Exception as e:
            logger.error(f"Error calculating heat wave risk: {e}")
            return 0.5  # Default moderate risk
    
    def get_state_level_risk(self, state_code: str) -> Dict[str, float]:
        """
        Get comprehensive state-level risk profile.
        
        Args:
            state_code: Indian state name
            
        Returns:
            Dictionary with monsoon_risk, cyclone_risk, heat_risk, region
        """
        if state_code in STATE_RISK_PROFILES:
            profile = STATE_RISK_PROFILES[state_code]
            return {
                "monsoon_risk": profile["monsoon_base"],
                "cyclone_risk": profile["cyclone_base"],
                "heat_risk": profile["heat_base"],
                "region": profile["region"],
            }
        else:
            logger.warning(f"Unknown state: {state_code}, returning default profile")
            return {
                "monsoon_risk": 0.5,
                "cyclone_risk": 0.3,
                "heat_risk": 0.5,
                "region": "unknown",
            }
    
    # Private helper methods
    
    def _estimate_monsoon_from_coords(self, lat: float, lon: float) -> Tuple[float, str]:
        """Estimate monsoon risk from coordinates when state is unknown."""
        # Coastal regions (high monsoon)
        if (lat >= 8 and lat <= 12 and lon >= 74 and lon <= 78):  # Kerala/Karnataka coast
            return 0.7, "coastal_southwest"
        elif (lat >= 8 and lat <= 13 and lon >= 78 and lon <= 81):  # Tamil Nadu coast
            return 0.6, "coastal_southeast"
        elif (lat >= 17 and lat <= 22 and lon >= 82 and lon <= 87):  # Odisha/West Bengal coast
            return 0.7, "coastal_east"
        # Inland regions
        elif (lat >= 24 and lat <= 30 and lon >= 70 and lon <= 76):  # Rajasthan
            return 0.3, "inland_northwest"
        # Default
        else:
            return 0.5, "inland_central"
    
    def _estimate_cyclone_from_coords(self, lat: float, lon: float) -> float:
        """Estimate cyclone risk from coordinates."""
        # Bay of Bengal coast (high cyclone risk)
        if (lat >= 8 and lat <= 22 and lon >= 80 and lon <= 88):
            return 0.7
        # Arabian Sea coast (moderate cyclone risk)
        elif (lat >= 8 and lat <= 23 and lon >= 68 and lon <= 76):
            return 0.5
        # Inland (no cyclone risk)
        else:
            return 0.0
    
    def _estimate_heat_from_coords(self, lat: float, lon: float) -> float:
        """Estimate heat risk from coordinates."""
        # Rajasthan/Gujarat (extreme heat)
        if (lat >= 23 and lat <= 30 and lon >= 69 and lon <= 76):
            return 0.9
        # Central India (high heat)
        elif (lat >= 18 and lat <= 26 and lon >= 74 and lon <= 84):
            return 0.7
        # Himalayan regions (low heat)
        elif (lat >= 28):
            return 0.2
        # Default moderate
        else:
            return 0.5
    
    def _get_enso_adjustment(self) -> float:
        """
        Get ENSO (El Niño-Southern Oscillation) phase adjustment.
        
        Returns:
            Adjustment factor (-0.2 to +0.3)
            El Niño: -0.2 (weaker monsoon)
            La Niña: +0.3 (stronger monsoon)
            Neutral: 0.0
        """
        # TODO: Integrate real-time ENSO data from NOAA or IMD
        # For now, return neutral
        return 0.0
