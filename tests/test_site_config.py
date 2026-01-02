"""
Tests for SiteConfig.
"""
import pytest
import json
from pathlib import Path
from sites.site_config import SiteConfig


@pytest.mark.unit
class TestSiteConfig:
    """Test suite for SiteConfig class."""

    @pytest.fixture
    def sample_config_data(self):
        """Sample site configuration data."""
        return {
            "sites": [
                {
                    "site_name": "athome",
                    "display_name": "AtHome",
                    "base_url": "https://www.athome.co.jp",
                    "enabled": True,
                    "rate_limit": {
                        "max_requests": 60,
                        "period_seconds": 300
                    },
                    "entry_urls": {
                        "nagano": "https://www.athome.co.jp/kodate/chuko/nagano/list/",
                        "yamanashi": "https://www.athome.co.jp/kodate/chuko/yamanashi/list/"
                    },
                    "selectors": {
                        "list_page": {
                            "property_container": ".property-list",
                            "property_item": ".property-item"
                        },
                        "detail_page": {
                            "title": "h1.title",
                            "price": ".price"
                        }
                    },
                    "pagination": {
                        "type": "page_param",
                        "param_name": "page",
                        "max_pages": 100
                    }
                },
                {
                    "site_name": "suumo",
                    "display_name": "SUUMO",
                    "base_url": "https://suumo.jp",
                    "enabled": False,
                    "rate_limit": {
                        "max_requests": 30,
                        "period_seconds": 300
                    },
                    "entry_urls": {
                        "tokyo": "https://suumo.jp/tokyo/list/"
                    },
                    "selectors": {
                        "list_page": {
                            "property_item": ".cassetteitem"
                        }
                    }
                },
                {
                    "site_name": "minimal_site",
                    "display_name": "Minimal Site",
                    "base_url": "https://minimal.com",
                    "enabled": True
                }
            ]
        }

    @pytest.fixture
    def config_file(self, temp_dir, sample_config_data):
        """Create a sample sites.json file."""
        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(sample_config_data, f, ensure_ascii=False, indent=2)
        return config_path

    def test_init_loads_config(self, config_file):
        """Test that initialization loads configuration."""
        site_config = SiteConfig(config_file)

        assert site_config.config_path == config_file
        assert len(site_config.sites) == 3
        assert "athome" in site_config.sites
        assert "suumo" in site_config.sites
        assert "minimal_site" in site_config.sites

    def test_init_file_not_found(self, temp_dir):
        """Test that FileNotFoundError is raised for missing config."""
        non_existent_path = Path(temp_dir) / "non_existent.json"

        with pytest.raises(FileNotFoundError, match="Site config not found"):
            SiteConfig(non_existent_path)

    def test_get_site_existing(self, config_file):
        """Test get_site returns correct configuration."""
        site_config = SiteConfig(config_file)

        athome = site_config.get_site("athome")

        assert athome is not None
        assert athome["site_name"] == "athome"
        assert athome["display_name"] == "AtHome"
        assert athome["base_url"] == "https://www.athome.co.jp"
        assert athome["enabled"] is True

    def test_get_site_non_existent(self, config_file):
        """Test get_site returns None for non-existent site."""
        site_config = SiteConfig(config_file)

        result = site_config.get_site("non_existent_site")

        assert result is None

    def test_get_enabled_sites(self, config_file):
        """Test get_enabled_sites returns only enabled sites."""
        site_config = SiteConfig(config_file)

        enabled = site_config.get_enabled_sites()

        assert "athome" in enabled
        assert "minimal_site" in enabled
        assert "suumo" not in enabled  # Disabled

    def test_get_enabled_sites_all_enabled(self, temp_dir):
        """Test get_enabled_sites when all sites are enabled."""
        config_data = {
            "sites": [
                {"site_name": "site1", "enabled": True},
                {"site_name": "site2", "enabled": True},
                {"site_name": "site3", "enabled": True},
            ]
        }

        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)

        site_config = SiteConfig(config_path)
        enabled = site_config.get_enabled_sites()

        assert len(enabled) == 3

    def test_get_enabled_sites_default(self, temp_dir):
        """Test get_enabled_sites defaults to enabled when field missing."""
        config_data = {
            "sites": [
                {"site_name": "site1"},  # No enabled field
                {"site_name": "site2", "enabled": False},
            ]
        }

        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)

        site_config = SiteConfig(config_path)
        enabled = site_config.get_enabled_sites()

        assert "site1" in enabled  # Default True
        assert "site2" not in enabled

    def test_get_entry_urls(self, config_file):
        """Test get_entry_urls returns correct URLs."""
        site_config = SiteConfig(config_file)

        urls = site_config.get_entry_urls("athome")

        assert urls["nagano"] == "https://www.athome.co.jp/kodate/chuko/nagano/list/"
        assert urls["yamanashi"] == "https://www.athome.co.jp/kodate/chuko/yamanashi/list/"

    def test_get_entry_urls_non_existent_site(self, config_file):
        """Test get_entry_urls returns empty dict for non-existent site."""
        site_config = SiteConfig(config_file)

        urls = site_config.get_entry_urls("non_existent")

        assert urls == {}

    def test_get_entry_urls_missing_field(self, config_file):
        """Test get_entry_urls when entry_urls field is missing."""
        # minimal_site doesn't have entry_urls
        site_config = SiteConfig(config_file)

        urls = site_config.get_entry_urls("minimal_site")

        assert urls == {}

    def test_get_selectors(self, config_file):
        """Test get_selectors returns correct selectors."""
        site_config = SiteConfig(config_file)

        list_selectors = site_config.get_selectors("athome", "list_page")
        detail_selectors = site_config.get_selectors("athome", "detail_page")

        assert list_selectors["property_container"] == ".property-list"
        assert list_selectors["property_item"] == ".property-item"
        assert detail_selectors["title"] == "h1.title"
        assert detail_selectors["price"] == ".price"

    def test_get_selectors_non_existent_site(self, config_file):
        """Test get_selectors returns empty dict for non-existent site."""
        site_config = SiteConfig(config_file)

        selectors = site_config.get_selectors("non_existent", "list_page")

        assert selectors == {}

    def test_get_selectors_non_existent_page_type(self, config_file):
        """Test get_selectors returns empty dict for non-existent page type."""
        site_config = SiteConfig(config_file)

        selectors = site_config.get_selectors("athome", "non_existent_page")

        assert selectors == {}

    def test_get_rate_limit(self, config_file):
        """Test get_rate_limit returns correct limits."""
        site_config = SiteConfig(config_file)

        athome_limits = site_config.get_rate_limit("athome")
        suumo_limits = site_config.get_rate_limit("suumo")

        assert athome_limits["max_requests"] == 60
        assert athome_limits["period_seconds"] == 300
        assert suumo_limits["max_requests"] == 30
        assert suumo_limits["period_seconds"] == 300

    def test_get_rate_limit_default(self, config_file):
        """Test get_rate_limit returns default for non-existent site."""
        site_config = SiteConfig(config_file)

        limits = site_config.get_rate_limit("non_existent")

        assert limits["max_requests"] == 30
        assert limits["period_seconds"] == 300

    def test_get_rate_limit_missing_field(self, config_file):
        """Test get_rate_limit returns default when field missing."""
        # minimal_site doesn't have rate_limit
        site_config = SiteConfig(config_file)

        limits = site_config.get_rate_limit("minimal_site")

        assert limits["max_requests"] == 30
        assert limits["period_seconds"] == 300

    def test_get_pagination(self, config_file):
        """Test get_pagination returns correct settings."""
        site_config = SiteConfig(config_file)

        pagination = site_config.get_pagination("athome")

        assert pagination["type"] == "page_param"
        assert pagination["param_name"] == "page"
        assert pagination["max_pages"] == 100

    def test_get_pagination_default(self, config_file):
        """Test get_pagination returns default for non-existent site."""
        site_config = SiteConfig(config_file)

        pagination = site_config.get_pagination("non_existent")

        assert pagination["type"] == "page_param"
        assert pagination["param_name"] == "page"
        assert pagination["max_pages"] == 100

    def test_get_pagination_missing_field(self, config_file):
        """Test get_pagination returns default when field missing."""
        # suumo doesn't have pagination
        site_config = SiteConfig(config_file)

        pagination = site_config.get_pagination("suumo")

        assert pagination["type"] == "page_param"
        assert pagination["param_name"] == "page"
        assert pagination["max_pages"] == 100

    def test_config_indexing_by_site_name(self, config_file):
        """Test that sites are indexed by site_name for easy lookup."""
        site_config = SiteConfig(config_file)

        # Should be able to access directly via site_name
        assert "athome" in site_config.sites
        assert site_config.sites["athome"]["display_name"] == "AtHome"

    def test_empty_config(self, temp_dir):
        """Test handling of empty configuration."""
        config_data = {"sites": []}

        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)

        site_config = SiteConfig(config_path)

        assert len(site_config.sites) == 0
        assert site_config.get_enabled_sites() == []

    def test_unicode_handling(self, temp_dir):
        """Test that Unicode characters are handled correctly."""
        config_data = {
            "sites": [
                {
                    "site_name": "test",
                    "display_name": "テストサイト",
                    "base_url": "https://example.jp"
                }
            ]
        }

        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False)

        site_config = SiteConfig(config_path)

        assert site_config.sites["test"]["display_name"] == "テストサイト"

    def test_pathlib_path_support(self, config_file):
        """Test that Path objects are supported for config_path."""
        # config_file is already a Path object
        site_config = SiteConfig(config_file)

        assert site_config.config_path == config_file
        assert len(site_config.sites) > 0

    @pytest.mark.parametrize("site_name,expected_enabled", [
        ("athome", True),
        ("suumo", False),
        ("minimal_site", True),
    ])
    def test_site_enabled_status(self, config_file, site_name, expected_enabled):
        """Test enabled status of various sites."""
        site_config = SiteConfig(config_file)
        site = site_config.get_site(site_name)

        assert site.get("enabled", True) == expected_enabled

    def test_multiple_entry_urls(self, temp_dir):
        """Test site with multiple entry URLs."""
        config_data = {
            "sites": [
                {
                    "site_name": "multi_url",
                    "entry_urls": {
                        "pref1": "https://example.com/pref1",
                        "pref2": "https://example.com/pref2",
                        "pref3": "https://example.com/pref3",
                    }
                }
            ]
        }

        config_path = Path(temp_dir) / "sites.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)

        site_config = SiteConfig(config_path)
        urls = site_config.get_entry_urls("multi_url")

        assert len(urls) == 3
        assert "pref1" in urls
        assert "pref2" in urls
        assert "pref3" in urls
