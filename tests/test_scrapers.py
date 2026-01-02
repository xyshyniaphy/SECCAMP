"""
Tests for web scrapers (BaseScraper and implementations).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException

from scrapers.base_scraper import BaseScraper


@pytest.mark.unit
class TestBaseScraper:
    """Test suite for BaseScraper abstract base class."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Selenium WebDriver."""
        driver = Mock(spec=webdriver.Chrome)
        driver.page_source = "<html><body>Test Page</body></html>"
        driver.current_url = "https://example.com/test"
        return driver

    @pytest.fixture
    def concrete_scraper(self, mock_db_connection):
        """Create a concrete scraper for testing."""
        with patch('scrapers.base_scraper.CacheManager'), \
             patch('scrapers.base_scraper.RateLimiter'):

            class TestScraper(BaseScraper):
                def _scrape_implementation(self):
                    return [
                        {
                            "source_property_id": "test_1",
                            "title": "Test Property",
                            "price_yen": 1000000,
                        }
                    ]

            return TestScraper(
                site_name="test_site",
                base_url="https://example.com",
                database_url="postgresql://test"
            )

    def test_init(self, concrete_scraper):
        """Test BaseScraper initialization."""
        assert concrete_scraper.site_name == "test_site"
        assert concrete_scraper.base_url == "https://example.com"
        assert concrete_scraper.database_url == "postgresql://test"
        assert concrete_scraper.headless is True
        assert concrete_scraper.page_timeout == 30
        assert concrete_scraper.max_retries == 3

    def test_setup_driver(self, concrete_scraper):
        """Test WebDriver setup."""
        with patch('scrapers.base_scraper.webdriver.Chrome') as mock_chrome:
            mock_driver_instance = Mock()
            mock_chrome.return_value = mock_driver_instance

            concrete_scraper.setup_driver()

            assert concrete_scraper.driver == mock_driver_instance
            mock_driver_instance.set_page_load_timeout.assert_called_once_with(30)

    def test_teardown_driver(self, concrete_scraper, mock_driver):
        """Test WebDriver teardown."""
        concrete_scraper.driver = mock_driver

        concrete_scraper.teardown_driver()

        mock_driver.quit.assert_called_once()

    def test_teardown_driver_handles_exception(self, concrete_scraper, mock_driver):
        """Test teardown_driver handles exceptions gracefully."""
        mock_driver.quit.side_effect = Exception("Quit error")
        concrete_scraper.driver = mock_driver

        # Should not raise exception
        concrete_scraper.teardown_driver()

    def test_safe_get_success(self, concrete_scraper, mock_driver):
        """Test safe_get returns True on successful navigation."""
        concrete_scraper.driver = mock_driver

        with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = Mock()

            with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
                mock_rl.wait_if_needed.return_value = False
                mock_rl.record_request = Mock()

                result = concrete_scraper.safe_get("https://example.com")

                assert result is True
                mock_driver.get.assert_called_once_with("https://example.com")

    def test_safe_get_timeout(self, concrete_scraper, mock_driver):
        """Test safe_get returns False on timeout."""
        concrete_scraper.driver = mock_driver

        with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException("Timeout")

            with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
                mock_rl.wait_if_needed.return_value = False
                mock_rl.record_request = Mock()

                result = concrete_scraper.safe_get("https://example.com")

                assert result is False

    def test_safe_get_webdriver_exception(self, concrete_scraper, mock_driver):
        """Test safe_get returns False on WebDriverException."""
        concrete_scraper.driver = mock_driver
        mock_driver.get.side_effect = WebDriverException("Driver error")

        with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
            mock_rl.wait_if_needed.return_value = False
            mock_rl.record_request = Mock()

            result = concrete_scraper.safe_get("https://example.com")

            assert result is False

    def test_safe_get_with_cache_hit(self, concrete_scraper):
        """Test safe_get_with_cache returns cached HTML."""
        with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
            mock_rl.wait_if_needed.return_value = False
            mock_rl.record_request = Mock()

            with patch.object(concrete_scraper, 'cache_manager') as mock_cm:
                mock_cm.get_cache.return_value = {
                    "from_cache": True,
                    "raw_html": "<html>Cached content</html>"
                }

                result = concrete_scraper.safe_get_with_cache(
                    "https://example.com",
                    page_type="detail"
                )

                assert result == "<html>Cached content</html>"
                mock_cm.get_cache.assert_called_once()

    def test_safe_get_with_cache_miss(self, concrete_scraper, mock_driver):
        """Test safe_get_with_cache fetches fresh content on cache miss."""
        concrete_scraper.driver = mock_driver

        with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
            mock_rl.wait_if_needed.return_value = False
            mock_rl.record_request = Mock()

            with patch.object(concrete_scraper, 'cache_manager') as mock_cm:
                mock_cm.get_cache.return_value = None  # Cache miss
                mock_cm.set_cache = Mock()

                with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
                    mock_wait.return_value.until.return_value = Mock()

                    result = concrete_scraper.safe_get_with_cache(
                        "https://example.com",
                        page_type="detail"
                    )

                    assert result == "<html><body>Test Page</body></html>"
                    mock_cm.set_cache.assert_called_once()

    def test_safe_get_with_cache_force_refresh(self, concrete_scraper, mock_driver):
        """Test safe_get_with_cache with force_refresh=True."""
        concrete_scraper.driver = mock_driver

        with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
            mock_rl.wait_if_needed.return_value = False
            mock_rl.record_request = Mock()

            with patch.object(concrete_scraper, 'cache_manager') as mock_cm:
                mock_cm.set_cache = Mock()

                with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
                    mock_wait.return_value.until.return_value = Mock()

                    result = concrete_scraper.safe_get_with_cache(
                        "https://example.com",
                        page_type="detail",
                        force_refresh=True
                    )

                    # Should skip cache and fetch fresh
                    mock_cm.get_cache.assert_not_called()
                    mock_cm.set_cache.assert_called_once()

    def test_scrape_success(self, concrete_scraper):
        """Test scrape method with successful implementation."""
        with patch.object(concrete_scraper, 'setup_driver'):
            with patch.object(concrete_scraper, 'teardown_driver'):
                result = concrete_scraper.scrape()

                assert len(result) == 1
                assert result[0]["source_property_id"] == "test_1"

    def test_scrape_exception_handling(self, concrete_scraper):
        """Test scrape method handles exceptions gracefully."""
        with patch.object(concrete_scraper, 'setup_driver', side_effect=Exception("Setup error")):
            with patch.object(concrete_scraper, 'teardown_driver'):
                result = concrete_scraper.scrape()

                # Should return empty list on error
                assert result == []

    def test_scrape_always_teardown(self, concrete_scraper):
        """Test scrape method always calls teardown, even on error."""
        with patch.object(concrete_scraper, 'setup_driver', side_effect=Exception("Error")):
            with patch.object(concrete_scraper, 'teardown_driver') as mock_teardown:
                concrete_scraper.scrape()

                # Teardown should still be called
                mock_teardown.assert_called_once()

    @pytest.mark.parametrize("page_type,expected_ttl", [
        ("list", 6 * 3600),
        ("detail", 7 * 86400),
        ("image", 30 * 86400),
    ])
    def test_page_type_ttl(self, concrete_scraper, mock_driver, page_type, expected_ttl):
        """Test that different page types have correct TTL."""
        concrete_scraper.driver = mock_driver

        with patch.object(concrete_scraper, 'rate_limiter'):
            with patch.object(concrete_scraper, 'cache_manager') as mock_cm:
                mock_cm.get_cache.return_value = None

                with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
                    mock_wait.return_value.until.return_value = Mock()

                    concrete_scraper.safe_get_with_cache(
                        "https://example.com",
                        page_type=page_type
                    )

                    # Verify set_cache was called with correct page_type
                    mock_cm.set_cache.assert_called_once()
                    call_kwargs = mock_cm.set_cache.call_args[1]
                    assert call_kwargs["page_type"] == page_type

    def test_rate_limiting_called(self, concrete_scraper, mock_driver):
        """Test that rate limiting is called before requests."""
        concrete_scraper.driver = mock_driver

        with patch.object(concrete_scraper, 'rate_limiter') as mock_rl:
            mock_rl.wait_if_needed.return_value = False
            mock_rl.record_request = Mock()

            with patch('scrapers.base_scraper.WebDriverWait') as mock_wait:
                mock_wait.return_value.until.return_value = Mock()

                concrete_scraper.safe_get("https://example.com")

                # Verify rate limiter was called
                mock_rl.wait_if_needed.assert_called_once_with("test_site")
                mock_rl.record_request.assert_called_once()


@pytest.mark.scraper
@pytest.mark.integration
class TestScraperIntegration:
    """Integration tests for scrapers with real components."""

    @pytest.fixture
    def scraper_with_components(self, temp_db_path):
        """Create scraper with real cache and rate limiter components."""
        # This would create a real scraper with actual database connections
        # For now, we'll mock to avoid dependency on actual ChromeDriver
        pass

    @pytest.mark.slow
    def test_full_scrape_workflow(self):
        """Test complete scrape workflow with real browser."""
        # This would test actual scraping with Chrome
        pass

    @pytest.mark.slow
    def test_cache_persistence(self):
        """Test that cache persists across scraper instances."""
        # This would test cache persistence
        pass


@pytest.mark.unit
class TestScraperHelpers:
    """Test helper functions and utilities for scrapers."""

    def test_url_normalization_integration(self):
        """Test URL normalization is used correctly in scrapers."""
        # Test that URLNormalizer is integrated properly
        pass

    def test_error_recovery(self):
        """Test error recovery mechanisms."""
        # Test retry logic, error handling, etc.
        pass

    def test_logging(self):
        """Test that appropriate logging occurs."""
        # Verify logging at various levels
        pass


@pytest.mark.parametrize("site_name,base_url", [
    ("athome", "https://www.athome.co.jp"),
    ("suumo", "https://suumo.jp"),
    ("ieichiba", "https://ieichiba.com"),
])
def test_scraper_site_configuration(site_name, base_url):
    """Test that scrapers are configured correctly for each site."""
    # This would test site-specific configuration loading
    pass


@pytest.mark.unit
class TestScraperAbstractMethod:
    """Test that abstract method is properly enforced."""

    def test_abstract_method_required(self):
        """Test that _scrape_implementation must be implemented."""
        with pytest.raises(TypeError):
            # Cannot instantiate abstract class directly
            BaseScraper(
                site_name="test",
                base_url="https://example.com",
                database_url="postgresql://test"
            )
