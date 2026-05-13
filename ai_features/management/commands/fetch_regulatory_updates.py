# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command to fetch regulatory updates manually.

Usage:
    python manage.py fetch_regulatory_updates
    python manage.py fetch_regulatory_updates --clear-cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from ai_features.regulatory_fetcher import fetch_and_save_regulatory_updates, RegulatoryDataFetcher


class Command(BaseCommand):
    help = "Fetch latest regulatory updates from EU SFDR and SEBI"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            help="Clear cached regulatory data before fetching",
        )
    
    def handle(self, *args, **options):
        # Clear cache if requested
        if options["clear_cache"]:
            self.stdout.write(self.style.WARNING("Clearing regulatory data cache..."))
            fetcher = RegulatoryDataFetcher()
            fetcher.clear_cache()
            self.stdout.write(self.style.SUCCESS("✓ Cache cleared"))
        
        self.stdout.write(self.style.WARNING("\nFetching regulatory updates..."))
        self.stdout.write("Sources:")
        self.stdout.write("  - EU SFDR: https://www.esma.europa.eu/press-news/esma-news")
        self.stdout.write("  - SEBI: https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doListing=yes&sid=2&ssid=3&smid=0")
        self.stdout.write("")
        
        try:
            result = fetch_and_save_regulatory_updates()
            
            if result["success"]:
                self.stdout.write(self.style.SUCCESS("\n" + "="*80))
                self.stdout.write(self.style.SUCCESS("REGULATORY UPDATES FETCH COMPLETE"))
                self.stdout.write(self.style.SUCCESS("="*80))
                
                self.stdout.write(f"\nUpdates Fetched: {result['updates_fetched']}")
                self.stdout.write(f"New Updates Saved: {result['updates_saved']}")
                self.stdout.write(f"Last Updated: {result['last_updated'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                # Cache the timestamp
                cache.set("regulatory_last_updated", result["last_updated"], timeout=None)
                
                self.stdout.write(self.style.SUCCESS("\n" + "="*80))
                self.stdout.write(self.style.SUCCESS("✓ Regulatory data updated successfully"))
                self.stdout.write(self.style.SUCCESS("="*80 + "\n"))
            else:
                self.stdout.write(self.style.ERROR(f"\n✗ Fetch failed: {result['error']}"))
                self.stdout.write(self.style.WARNING("\nPossible reasons:"))
                self.stdout.write("  1. Network connection issues")
                self.stdout.write("  2. Website structure changed")
                self.stdout.write("  3. Rate limiting or blocking")
                self.stdout.write("\nCheck logs for details.\n")
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Unexpected error: {e}"))
            import traceback
            traceback.print_exc()
