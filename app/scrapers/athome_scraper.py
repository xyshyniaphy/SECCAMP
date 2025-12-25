"""Athome.co.jp scraper - scrape only, no parsing (for debugging)."""
import logging
import re
from typing import Any, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class AthomeScraper(BaseScraper):
    """
    Athome.co.jp scraper - DEBUG VERSION.

    This version only scrapes HTML and saves it for inspection.
    No parsing logic is implemented yet.
    """

    # Default to nagano prefecture for testing
    DEFAULT_PREF = "nagano"

    def __init__(
        self,
        database_url: str,
        max_detail_pages: int = 1,
        pref_name: str = DEFAULT_PREF,
    ):
        # Load site config
        import sys
        from pathlib import Path
        # Add app directory to path for imports
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from sites.site_config import SiteConfig

        site_config = SiteConfig()
        athome_config = site_config.get_site("athome")

        if not athome_config:
            raise ValueError("Athome site configuration not found in sites/sites.json")

        base_url = athome_config["base_url"]
        super().__init__(
            site_name="athome",
            base_url=base_url,
            database_url=database_url,
        )

        self.max_detail_pages = max_detail_pages
        self.pref_name = pref_name
        self.entry_urls = athome_config.get("entry_urls", {})
        self.selectors = athome_config.get("selectors", {})
        self.pagination = athome_config.get("pagination", {})

        # Get entry URL for the prefecture
        self.entry_url = self.entry_urls.get(pref_name)
        if not self.entry_url:
            available = list(self.entry_urls.keys())
            raise ValueError(
                f"Prefecture '{pref_name}' not found. Available: {available}"
            )

        logger.info(f"AthomeScraper initialized: pref={pref_name}, max_detail_pages={max_detail_pages}")

    def _scrape_implementation(self) -> Dict[str, Any]:
        """
        Main scrape implementation - DEBUG VERSION.

        Returns:
            Dict with scraped HTML for inspection:
            - list_html: Raw HTML from list page
            - property_urls: List of property detail URLs found
            - detail_pages: Dict mapping URL to raw HTML
        """
        result = {
            "prefecture": self.pref_name,
            "list_url": self.entry_url,
            "list_html": None,
            "property_urls": [],
            "detail_pages": {},
        }

        # Step 1: Scrape list page
        logger.info(f"[*] Scraping list page: {self.entry_url}")
        list_html = self.safe_get_with_cache(self.entry_url, page_type="list")

        if not list_html:
            logger.error("Failed to fetch list page")
            return result

        result["list_html"] = list_html
        logger.info(f"[*] List page HTML size: {len(list_html)} bytes")

        # Step 2: Extract property URLs
        property_urls = self._extract_property_urls(list_html)
        result["property_urls"] = property_urls
        logger.info(f"[*] Found {len(property_urls)} property URLs")

        if not property_urls:
            logger.warning("No property URLs found")
            return result

        # Step 3: Scrape detail pages (limited by max_detail_pages)
        limit = min(self.max_detail_pages, len(property_urls))
        logger.info(f"[*] Scraping {limit} detail page(s) (max={self.max_detail_pages})")

        for i, url in enumerate(property_urls[:limit]):
            logger.info(f"[*] Scraping detail page {i + 1}/{limit}: {url}")
            detail_html = self.safe_get_with_cache(url, page_type="detail")

            if detail_html:
                result["detail_pages"][url] = detail_html
                logger.info(f"    HTML size: {len(detail_html)} bytes")
            else:
                logger.error(f"    Failed to fetch: {url}")

        return result

    def _extract_property_urls(self, list_html: str) -> list[str]:
        """
        Extract property detail URLs from list page HTML.

        Pattern: /kodate/{digits}/
        """
        soup = BeautifulSoup(list_html, "lxml")
        urls = set()  # Use set to deduplicate

        # Find all links matching the property pattern
        for link in soup.find_all("a", href=re.compile(r"/kodate/\d+/")):
            href = link.get("href")
            if href:
                full_url = urljoin(self.base_url, href)
                urls.add(full_url)

        result = sorted(urls)  # Sort for consistency
        logger.info(f"[*] Extracted {len(result)} unique property URLs")
        return result
