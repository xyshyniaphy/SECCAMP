"""Base scraper class for real estate sites."""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for real estate site scrapers."""

    def __init__(
        self,
        site_name: str,
        base_url: str,
        headless: bool = True,
        page_timeout: int = 30,
    ):
        self.site_name = site_name
        self.base_url = base_url
        self.headless = headless
        self.page_timeout = page_timeout
        self.driver: Optional[webdriver.Chrome] = None
        self.max_retries = 3

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
        """Safely navigate to URL with error handling."""
        try:
            self.driver.get(url)
            logger.info(f"Successfully loaded: {url}")
            return True
        except TimeoutException:
            logger.warning(f"Timeout loading: {url}")
            return False
        except WebDriverException as e:
            logger.error(f"WebDriver error loading {url}: {e}")
            return False

    def scrape(self) -> List[Dict]:
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
    def _scrape_implementation(self) -> List[Dict]:
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
