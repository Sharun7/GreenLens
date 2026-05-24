# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/worldbank_fetcher.py — WorldBank bond data fetcher.
"""
import requests
from datetime import datetime

class WorldBankBondFetcher:
    API_URL = "https://datacatalogapi.worldbank.org/dexapps/fone/api/apiservice?datasetId=DS00052&resourceId=RS00054&type=json"
    
    def fetch_all_bonds(self):
        """Fetch all 13,320 bonds from World Bank API"""
        response = requests.get(self.API_URL, timeout=60)
        data = response.json()
        return data.get('data', [])
    
    def map_to_greenbond(self, bond_data):
        """Map World Bank API fields to GreenBond model"""
        
        # Map currency to country
        CURRENCY_COUNTRY = {
            'INR': ('India', 'IN', 20.5937, 78.9629),
            'BRL': ('Brazil', 'BR', -14.235, -51.9253),
            'ZAR': ('South Africa', 'ZA', -30.5595, 22.9375),
            'NGN': ('Nigeria', 'NG', 9.082, 8.6753),
            'KZT': ('Kazakhstan', 'KZ', 48.0196, 66.9237),
            'COP': ('Colombia', 'CO', 4.5709, -74.2973),
            'PHP': ('Philippines', 'PH', 12.8797, 121.7740),
            'CLP': ('Chile', 'CL', -35.6751, -71.543),
            'UYU': ('Uruguay', 'UY', -32.5228, -55.7658),
            'HKD': ('Hong Kong', 'HK', 22.3193, 114.1694),
            'CNH': ('China', 'CN', 35.8617, 104.1954),
            'AUD': ('Australia', 'AU', -25.2744, 133.7751),
            'CAD': ('Canada', 'CA', 56.1304, -106.3468),
            'CHF': ('Switzerland', 'CH', 46.8182, 8.2275),
            'NOK': ('Norway', 'NO', 60.472, 8.4689),
            'EUR': ('Europe', 'EU', 50.8503, 4.3517),
            'GBP': ('United Kingdom', 'GB', 55.3781, -3.4360),
            'USD': ('United States', 'US', 37.0902, -95.7129),
        }
        
        currency = bond_data.get('denominated_currency', 'USD')
        country_info = CURRENCY_COUNTRY.get(currency, 
                       ('International', 'INT', 38.8951, -77.0364))
        
        # Map bond type to project category
        bond_type = bond_data.get('type', '')
        if 'Green' in bond_type:
            category = 'other'
        else:
            category = 'other'
        
        # Parse dates
        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, '%d-%b-%Y').date()
            except:
                return None
        
        settlement = parse_date(bond_data.get('settlement_date'))
        
        return {
            'bond_id': f"WB_{bond_data.get('isin', '')}",
            'issuer_name': 'World Bank (IBRD)',
            'country': country_info[0],
            'project_category': category,
            'project_description': f"World Bank IBRD {bond_data.get('type', '')} bond",
            'bond_maturity_years': max(1, int(bond_data.get('maturity', 5))),
            'issuance_date': settlement,
            'currency': currency[:3],
            'amount_millions': round(
                (bond_data.get('usd_equivalent', 0) or 0) / 1_000_000, 2
            ),
            'lat': country_info[2],
            'lon': country_info[3],
            'location_confidence': 'country',
            'regulatory_framework': 'OTHER',
            'disclosure_quality': 'LOW',
            'data_source': 'WorldBank',
        }
    
    def sync_to_database(self, limit=None):
        """Fetch and save World Bank bonds to GreenBond model"""
        from data_ingestion.models import GreenBond
        
        bonds_data = self.fetch_all_bonds()
        if limit:
            bonds_data = bonds_data[:limit]
        
        added = 0
        skipped = 0
        
        for bond_data in bonds_data:
            isin = bond_data.get('isin')
            if not isin:
                continue
            
            mapped = self.map_to_greenbond(bond_data)
            
            if not mapped.get('issuance_date'):
                skipped += 1
                continue
            
            _, created = GreenBond.objects.update_or_create(
                bond_id=mapped['bond_id'],
                defaults=mapped
            )
            if created:
                added += 1
        
        return {
            'added': added,
            'skipped': skipped,
            'total_processed': len(bonds_data)
        }
