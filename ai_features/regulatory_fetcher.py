# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
ai_features/regulatory_fetcher.py — Real regulatory data fetcher.

Fetches regulatory updates from:
1. EU SFDR - ESMA press news
2. SEBI - Green bond circulars

Caches results in Redis for 24 hours.
"""
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from django.core.cache import cache
from django.utils import timezone

from ai_features.models import RegulatoryMonitor

logger = logging.getLogger("greenlens.regulatory_fetcher")


class RegulatoryDataFetcher:
    """
    Fetch regulatory updates from official sources.
    """
    
    # Cache keys
    CACHE_KEY_EU = "regulatory_updates_eu"
    CACHE_KEY_SEBI = "regulatory_updates_sebi"
    CACHE_TTL = 86400  # 24 hours
    
    # URLs
    EU_SFDR_URL = "https://www.esma.europa.eu/press-news/esma-news"
    SEBI_CIRCULARS_URL = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doListing=yes&sid=2&ssid=3&smid=0"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GreenLens/1.0 (regulatory-monitoring; +https://greenlens.io)"
        })
    
    def fetch_all(self) -> Dict[str, List[Dict]]:
        """
        Fetch all regulatory updates.
        
        Returns:
            {
                "eu_updates": [...],
                "sebi_updates": [...],
                "total_count": int,
                "last_updated": datetime,
            }
        """
        logger.info("Fetching regulatory updates from all sources...")
        
        eu_updates = self.fetch_eu_sfdr()
        sebi_updates = self.fetch_sebi_circulars()
        
        result = {
            "eu_updates": eu_updates,
            "sebi_updates": sebi_updates,
            "total_count": len(eu_updates) + len(sebi_updates),
            "last_updated": timezone.now(),
        }
        
        logger.info(f"Fetched {result['total_count']} regulatory updates")
        return result
    
    def fetch_eu_sfdr(self) -> List[Dict]:
        """
        Fetch EU SFDR updates from ESMA press news.
        
        Returns:
            List of regulatory updates
        """
        # Check cache first
        cached = cache.get(self.CACHE_KEY_EU)
        if cached:
            logger.info("Using cached EU SFDR updates")
            return cached
        
        logger.info(f"Fetching EU SFDR updates from {self.EU_SFDR_URL}")
        
        try:
            response = self.session.get(self.EU_SFDR_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "html.parser")
            updates = []
            
            # Parse ESMA news items
            # ESMA structure: <div class="views-row"> containing news items
            news_items = soup.find_all("div", class_="views-row")
            
            for item in news_items[:10]:  # Limit to 10 most recent
                try:
                    # Extract title
                    title_elem = item.find("h3") or item.find("h2") or item.find("a")
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    
                    # Filter for SFDR/green bond/sustainability related
                    if not self._is_relevant_eu(title):
                        continue
                    
                    # Extract link
                    link_elem = item.find("a")
                    link = link_elem.get("href", "") if link_elem else ""
                    if link and not link.startswith("http"):
                        link = f"https://www.esma.europa.eu{link}"
                    
                    # Extract date
                    date_elem = item.find("span", class_="date") or item.find("time")
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        published_date = self._parse_date(date_text)
                    else:
                        published_date = timezone.now().date()
                    
                    # Extract description
                    desc_elem = item.find("p") or item.find("div", class_="field-content")
                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else title
                    
                    updates.append({
                        "source": "eu_sfdr",
                        "title": title,
                        "description": description,
                        "url": link,
                        "published_date": published_date,
                    })
                
                except Exception as e:
                    logger.warning(f"Failed to parse EU news item: {e}")
                    continue
            
            # Cache results
            cache.set(self.CACHE_KEY_EU, updates, self.CACHE_TTL)
            logger.info(f"Fetched {len(updates)} EU SFDR updates")
            
            return updates
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch EU SFDR updates: {e}")
            return []
        
        except Exception as e:
            logger.error(f"Unexpected error fetching EU SFDR updates: {e}")
            return []
    
    def fetch_sebi_circulars(self) -> List[Dict]:
        """
        Fetch SEBI green bond circulars.
        
        Returns:
            List of regulatory updates
        """
        # Check cache first
        cached = cache.get(self.CACHE_KEY_SEBI)
        if cached:
            logger.info("Using cached SEBI circulars")
            return cached
        
        logger.info(f"Fetching SEBI circulars from {self.SEBI_CIRCULARS_URL}")
        
        try:
            response = self.session.get(self.SEBI_CIRCULARS_URL, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "html.parser")
            updates = []
            
            # Parse SEBI circular table
            # SEBI structure: <table> with rows containing circulars
            table = soup.find("table")
            if not table:
                logger.warning("No table found on SEBI circulars page")
                return []
            
            rows = table.find_all("tr")[1:]  # Skip header row
            
            for row in rows[:10]:  # Limit to 10 most recent
                try:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue
                    
                    # Extract date (usually first column)
                    date_text = cells[0].get_text(strip=True)
                    published_date = self._parse_date(date_text)
                    
                    # Extract title (usually second or third column)
                    title_elem = cells[1].find("a") or cells[2].find("a")
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    
                    # Filter for green bond related
                    if not self._is_relevant_sebi(title):
                        continue
                    
                    # Extract link
                    link = title_elem.get("href", "")
                    if link and not link.startswith("http"):
                        link = f"https://www.sebi.gov.in{link}"
                    
                    # Description is usually the title for SEBI
                    description = title
                    
                    updates.append({
                        "source": "sebi_brsr",
                        "title": title,
                        "description": description,
                        "url": link,
                        "published_date": published_date,
                    })
                
                except Exception as e:
                    logger.warning(f"Failed to parse SEBI circular row: {e}")
                    continue
            
            # Cache results
            cache.set(self.CACHE_KEY_SEBI, updates, self.CACHE_TTL)
            logger.info(f"Fetched {len(updates)} SEBI circulars")
            
            return updates
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch SEBI circulars: {e}")
            return []
        
        except Exception as e:
            logger.error(f"Unexpected error fetching SEBI circulars: {e}")
            return []
    
    def _is_relevant_eu(self, text: str) -> bool:
        """Check if EU news is relevant to green bonds."""
        keywords = [
            "sfdr", "sustainable finance", "disclosure regulation",
            "green bond", "taxonomy", "esg", "sustainability",
            "climate", "environmental", "article 8", "article 9",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def _is_relevant_sebi(self, text: str) -> bool:
        """Check if SEBI circular is relevant to green bonds."""
        keywords = [
            "green bond", "green debt", "sustainability",
            "esg", "climate", "environmental", "brsr",
            "sustainable finance", "disclosure",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def _parse_date(self, date_text: str) -> datetime.date:
        """
        Parse date from various formats.
        
        Handles:
        - "10 May 2026"
        - "10/05/2026"
        - "2026-05-10"
        - "May 10, 2026"
        """
        date_text = date_text.strip()
        
        # Try common formats
        formats = [
            "%d %B %Y",      # 10 May 2026
            "%d %b %Y",      # 10 May 2026
            "%d/%m/%Y",      # 10/05/2026
            "%Y-%m-%d",      # 2026-05-10
            "%B %d, %Y",     # May 10, 2026
            "%b %d, %Y",     # May 10, 2026
            "%d-%m-%Y",      # 10-05-2026
            "%d.%m.%Y",      # 10.05.2026
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt).date()
            except ValueError:
                continue
        
        # If all parsing fails, return today
        logger.warning(f"Could not parse date: {date_text}")
        return timezone.now().date()
    
    def save_to_database(self, updates: Dict[str, List[Dict]]) -> int:
        """
        Save fetched updates to RegulatoryMonitor model.
        
        Returns:
            Number of new updates saved
        """
        saved_count = 0
        
        all_updates = updates["eu_updates"] + updates["sebi_updates"]
        
        for update in all_updates:
            # Check if already exists
            existing = RegulatoryMonitor.objects.filter(
                title=update["title"],
                announcement_date=update["published_date"],
            ).first()
            
            if existing:
                logger.debug(f"Update already exists: {update['title']}")
                continue
            
            # Map source to regulation type
            regulation_type_map = {
                "eu_sfdr": "eu_sfdr",
                "sebi_brsr": "sebi_brsr",
            }
            
            regulation_type = regulation_type_map.get(update["source"], "eu_sfdr")
            
            # Estimate effective date (6 months after announcement)
            effective_date = update["published_date"] + timedelta(days=180)
            
            # Create entry
            RegulatoryMonitor.objects.create(
                regulation_type=regulation_type,
                title=update["title"],
                description=update["description"],
                announcement_date=update["published_date"],
                effective_date=effective_date,
                impact_description=f"New {update['source'].upper()} regulation affecting green bond disclosure requirements.",
                affected_bonds_count=None,  # Will be calculated later
                compliance_required=True,
                action_required="Review disclosure templates and update reporting procedures.",
                source_url=update.get("url", ""),
            )
            
            saved_count += 1
            logger.info(f"Saved regulatory update: {update['title']}")
        
        logger.info(f"Saved {saved_count} new regulatory updates to database")
        return saved_count
    
    def clear_cache(self):
        """Clear cached regulatory data."""
        cache.delete(self.CACHE_KEY_EU)
        cache.delete(self.CACHE_KEY_SEBI)
        logger.info("Cleared regulatory data cache")


def fetch_and_save_regulatory_updates() -> Dict[str, any]:
    """
    Main entry point for fetching regulatory updates.
    
    Returns:
        {
            "success": bool,
            "updates_fetched": int,
            "updates_saved": int,
            "last_updated": datetime,
            "error": str or None,
        }
    """
    logger.info("Starting regulatory data fetch...")
    
    try:
        fetcher = RegulatoryDataFetcher()
        
        # Fetch updates
        updates = fetcher.fetch_all()
        
        # Save to database
        saved_count = fetcher.save_to_database(updates)
        
        result = {
            "success": True,
            "updates_fetched": updates["total_count"],
            "updates_saved": saved_count,
            "last_updated": updates["last_updated"],
            "error": None,
        }
        
        logger.info(f"Regulatory fetch complete: {saved_count} new updates saved")
        return result
    
    except Exception as e:
        logger.error(f"Regulatory fetch failed: {e}", exc_info=True)
        return {
            "success": False,
            "updates_fetched": 0,
            "updates_saved": 0,
            "last_updated": None,
            "error": str(e),
        }
