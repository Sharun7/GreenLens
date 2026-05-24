# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
data_ingestion/management/commands/sync_worldbank_bonds.py — Sync World Bank bonds command.
"""
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Sync World Bank bonds from free API'
    
    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, 
                          help='Limit number of bonds')
    
    def handle(self, *args, **options):
        from data_ingestion.worldbank_fetcher import WorldBankBondFetcher
        fetcher = WorldBankBondFetcher()
        self.stdout.write('Fetching World Bank bonds...')
        result = fetcher.sync_to_database(
            limit=options.get('limit')
        )
        self.stdout.write(
            f"Done: {result['added']} added, "
            f"{result['skipped']} skipped"
        )
