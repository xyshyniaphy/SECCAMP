"""Base scraper class for real estate sites (Neon PostgreSQL)."""
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging

from .cache_manager import CacheManager
from .rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for real estate site scrapers."""

    def __init__(
        self,
        site_name: str,
        base_url: str,
        database_url: str,
        headless: bool = True,
        page_timeout: int = 30,
    ):
        self.site_name = site_name
        self.base_url = base_url
        self.database_url = database_url
        self.headless = headless
        self.page_timeout = page_timeout
        self.driver: Optional[webdriver.Chrome] = None
        self.max_retries = 3

        # Initialize cache and rate limiter with database_url
        self.cache_manager = CacheManager(database_url)
        self.rate_limiter = RateLimiter(database_url)

    def setup_driver(self) -> None:
        """Initialize Chrome WebDriver with appropriate options."""
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-images")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.page_timeout)
        logger.info(f"WebDriver initialized for {self.site_name}")

    def teardown_driver(self) -> None:
        """Clean up WebDriver resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info(f"WebDriver closed for {self.site_name}")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")

    def safe_get(self, url: str) -> bool:
        """
        Safely navigate to URL with error handling and rate limiting.

        Args:
            url: URL to navigate to

        Returns:
            True if successful, False otherwise
        """
        self.rate_limiter.wait_if_needed(self.site_name)

        start_time = time.time()

        try:
            self.driver.get(url)

            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            duration_ms = int((time.time() - start_time) * 1000)

            self.rate_limiter.record_request(
                self.site_name,
                status="success",
                response_time_ms=duration_ms,
                from_cache=False,
            )

            logger.info(f"Loaded: {url} ({duration_ms}ms)")
            return True

        except TimeoutException:
            duration_ms = int((time.time() - start_time) * 1000)
            self.rate_limiter.record_request(
                self.site_name,
                status="timeout",
                response_time_ms=duration_ms,
                error_message="Page load timeout",
            )
            logger.warning(f"Timeout loading: {url}")
            return False

        except WebDriverException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.rate_limiter.record_request(
                self.site_name,
                status="failed",
                response_time_ms=duration_ms,
                error_message=str(e),
            )
            logger.error(f"WebDriver error loading {url}: {e}")
            return False

    def safe_get_with_cache(
        self,
        url: str,
        page_type: str = "detail",
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Get page HTML with multi-layered caching support.

        Layer 1: Check DB metadata
        Layer 2: Read HTML from local UUID file (if cache hit)
        Layer 3: Fetch from web (if cache miss)

        Args:
            url: URL to fetch
            page_type: Type of page ('list', 'detail', 'image')
            force_refresh: Skip cache and fetch fresh

        Returns:
            HTML content or None if failed
        """
        # Try cache first (DB metadata + local file)
        if not force_refresh:
            cached = self.cache_manager.get_cache(url, self.site_name, page_type)
            if cached and cached.get("from_cache") and cached.get("raw_html"):
                self.rate_limiter.record_request(
                    self.site_name,
                    status="success",
                    from_cache=True,
                )
                logger.debug(f"Cache HIT: {url}")
                return cached["raw_html"]

        # Cache miss - fetch fresh from web
        self.rate_limiter.wait_if_needed(self.site_name)

        start_time = time.time()

        try:
            self.driver.get(url)

            # Wait for page load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            html = self.driver.page_source
            duration_ms = int((time.time() - start_time) * 1000)

            # Store in cache (DB metadata + local UUID file)
            self.cache_manager.set_cache(
                url=url,
                site_name=self.site_name,
                page_type=page_type,
                http_status=200,
                raw_html=html,
                duration_ms=duration_ms,
            )

            # Record request
            self.rate_limiter.record_request(
                self.site_name,
                status="success",
                response_time_ms=duration_ms,
                from_cache=False,
            )

            logger.debug(f"Fetched: {url} ({duration_ms}ms)")
            return html

        except TimeoutException:
            duration_ms = int((time.time() - start_time) * 1000)
            self.rate_limiter.record_request(
                self.site_name,
                status="timeout",
                response_time_ms=duration_ms,
                error_message="Page load timeout",
            )
            logger.warning(f"Timeout loading: {url}")
            return None

        except WebDriverException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.rate_limiter.record_request(
                self.site_name,
                status="failed",
                response_time_ms=duration_ms,
                error_message=str(e),
            )
            logger.error(f"WebDriver error loading {url}: {e}")
            return None

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Main scrape method with setup/teardown.

        Returns:
            List of property dictionaries.
        """
        try:
            self.setup_driver()
            properties = self._scrape_implementation()
            logger.info(f"{self.site_name}: Scraped {len(properties)} properties")
            return properties
        except Exception as e:
            logger.error(f"{self.site_name}: Scrape failed with error: {e}")
            return []
        finally:
            self.teardown_driver()

    @abstractmethod
    def _scrape_implementation(self) -> List[Dict[str, Any]]:
        """
        Site-specific scraping logic to be implemented by subclasses.

        Returns:
            List of property dictionaries with keys:
            - source_property_id: str
            - property_name: str
            - location_pref: str
            - location_city: str
            - area_sqm: int
            - price_yen: int
            - is_free: bool
            - road_width_m: float
            - population_density: float
            - nearest_house_distance_m: int
        """
        pass
