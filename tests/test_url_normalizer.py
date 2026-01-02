"""
Tests for URLNormalizer.
"""
import pytest
from scrapers.url_normalizer import URLNormalizer


@pytest.mark.unit
class TestURLNormalizer:
    """Test suite for URLNormalizer class."""

    def test_normalize_basic_url(self):
        """Test basic URL normalization."""
        url = "https://www.example.com/property/12345"
        result = URLNormalizer.normalize(url)

        assert "original_url" in result
        assert "normalized_url" in result
        assert "url_hash" in result
        assert result["original_url"] == url
        assert result["normalized_url"] == url
        assert len(result["url_hash"]) == 64  # SHA256 hash length

    def test_normalize_case_insensitive(self):
        """Test that URL normalization handles case correctly."""
        url1 = "HTTPS://WWW.EXAMPLE.COM/PROPERTY/12345"
        url2 = "https://www.example.com/PROPERTY/12345"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        assert result1["normalized_url"] == result2["normalized_url"]
        assert result1["url_hash"] == result2["url_hash"]

    def test_normalize_trailing_slash(self):
        """Test that trailing slashes are removed."""
        url1 = "https://www.example.com/property/12345"
        url2 = "https://www.example.com/property/12345/"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        assert result1["normalized_url"] == result2["normalized_url"]
        assert result1["url_hash"] == result2["url_hash"]

    def test_normalize_query_params_default(self):
        """Test query parameter filtering with default settings."""
        url1 = "https://www.example.com/property/12345?utm_source=google&page=1"
        url2 = "https://www.example.com/property/12345?utm_source=bing&page=1"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        # Default params should filter utm_* but keep page
        assert result1["normalized_url"] == result2["normalized_url"]
        assert result1["url_hash"] == result2["url_hash"]

    def test_normalize_query_params_sorted(self):
        """Test that query parameters are sorted."""
        url1 = "https://www.example.com/property?b=2&a=1&c=3"
        url2 = "https://www.example.com/property?a=1&b=2&c=3"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        assert result1["normalized_url"] == result2["normalized_url"]
        assert result1["normalized_url"] == "https://www.example.com/property?a=1&b=2&c=3"

    def test_normalize_site_specific_params_athome(self):
        """Test site-specific parameter filtering for athome."""
        url = "https://www.athome.co.jp/kodate/12345/?DOWN=1&bb=1&utm_source=test"

        result = URLNormalizer.normalize(url, site_name="athome")

        # Should keep DOWN and bb, remove utm_source
        assert "DOWN=1" in result["normalized_url"]
        assert "bb=1" in result["normalized_url"]
        assert "utm_source" not in result["normalized_url"]

    def test_normalize_site_specific_params_suumo(self):
        """Test site-specific parameter filtering for suumo."""
        url = "https://suumo.jp/property/?bc=1000&ta=12&utm_source=test"

        result = URLNormalizer.normalize(url, site_name="suumo")

        # Should keep bc and ta, remove utm_source
        assert "bc=1000" in result["normalized_url"]
        assert "ta=12" in result["normalized_url"]
        assert "utm_source" not in result["normalized_url"]

    def test_normalize_empty_query_params(self):
        """Test URL with no query parameters."""
        url = "https://www.example.com/property/12345"
        result = URLNormalizer.normalize(url)

        assert "?" not in result["normalized_url"]
        assert result["normalized_url"] == url

    def test_normalize_with_fragment(self):
        """Test that URL fragments are removed."""
        url1 = "https://www.example.com/property/12345#section"
        url2 = "https://www.example.com/property/12345"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        assert "#" not in result1["normalized_url"]
        assert result1["normalized_url"] == result2["normalized_url"]

    def test_normalize_different_urls_different_hashes(self):
        """Test that different URLs produce different hashes."""
        url1 = "https://www.example.com/property/12345"
        url2 = "https://www.example.com/property/67890"

        result1 = URLNormalizer.normalize(url1)
        result2 = URLNormalizer.normalize(url2)

        assert result1["url_hash"] != result2["url_hash"]

    def test_normalize_same_urls_same_hashes(self):
        """Test that identical URLs produce same hashes."""
        url = "https://www.example.com/property/12345"

        result1 = URLNormalizer.normalize(url)
        result2 = URLNormalizer.normalize(url)

        assert result1["url_hash"] == result2["url_hash"]

    def test_normalize_preserves_essential_params(self):
        """Test that essential parameters are preserved."""
        url = "https://www.example.com/search?page=2&sort=price_desc&filter=active"

        result = URLNormalizer.normalize(url)

        assert "page=2" in result["normalized_url"]
        assert "sort=price_desc" in result["normalized_url"]
        assert "filter=active" in result["normalized_url"]

    def test_normalize_multiple_values_same_param(self):
        """Test handling of multiple values for same parameter."""
        url = "https://www.example.com/search?cat=1&cat=2&cat=3"

        result = URLNormalizer.normalize(url)

        # Multiple values should be preserved
        assert "cat=1" in result["normalized_url"]
        assert "cat=2" in result["normalized_url"]
        assert "cat=3" in result["normalized_url"]

    def test_normalize_blank_values(self):
        """Test handling of blank parameter values."""
        url = "https://www.example.com/search?key=&other=value"

        result = URLNormalizer.normalize(url)

        # Blank values should be preserved
        assert "key=" in result["normalized_url"] or "key" in result["normalized_url"]
        assert "other=value" in result["normalized_url"]

    def test_normalize_url_encoding(self):
        """Test that URL encoding is handled correctly."""
        url = "https://www.example.com/search?q=%E6%9C%AC%E7%94%BA"

        result = URLNormalizer.normalize(url)

        assert result["normalized_url"] == url
        assert len(result["url_hash"]) == 64

    def test_normalize_complex_url(self):
        """Test normalization of complex real-world URL."""
        url = "HTTPS://WWW.ATHOME.CO.JP/KODATE/12345/?DOWN=1&BB=1&NC=&TM=1"

        result = URLNormalizer.normalize(url, site_name="athome")

        assert result["normalized_url"].startswith("https://www.athome.co.jp")
        assert "DOWN=1" in result["normalized_url"]
        assert "BB=1" in result["normalized_url"]
        assert len(result["url_hash"]) == 64

    @pytest.mark.parametrize("url,expected_hash_length", [
        ("https://example.com", 64),
        ("https://example.com/very/long/path/that/keeps/going", 64),
        ("https://example.com?with=many&params=here&and=more", 64),
    ])
    def test_hash_length_consistency(self, url, expected_hash_length):
        """Test that hash length is always consistent."""
        result = URLNormalizer.normalize(url)
        assert len(result["url_hash"]) == expected_hash_length

    @pytest.mark.parametrize("site_name,url,expected_keeps", [
        ("athome", "https://athome.co.jp/?DOWN=1&test=1", ["DOWN"]),
        ("suumo", "https://suumo.jp/?bc=1000&test=1", ["bc"]),
        ("default", "https://example.com/?page=1&test=1", ["page"]),
    ])
    def test_site_specific_keeps(self, site_name, url, expected_keeps):
        """Test that site-specific parameters are correctly kept."""
        result = URLNormalizer.normalize(url, site_name=site_name)

        for expected in expected_keeps:
            assert f"{expected}=" in result["normalized_url"]
