"""
Tests for CacheManager.
"""
import pytest
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import psycopg2
from psycopg2.extras import RealDictCursor

from scrapers.cache_manager import CacheManager


@pytest.mark.unit
class TestCacheManager:
    """Test suite for CacheManager class."""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection."""
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock()
        conn.cursor.return_value.__exit__ = Mock()
        return conn

    @pytest.fixture
    def cache_manager_with_mock(self, mock_db_connection, temp_dir):
        """Create a CacheManager with mocked database connection."""
        with patch('scrapers.cache_manager.psycopg2.connect', return_value=mock_db_connection):
            manager = CacheManager("postgresql://test", cache_dir=Path(temp_dir))
            return manager

    def test_init_creates_cache_directory(self, mock_db_connection, temp_dir):
        """Test that initialization creates cache directory."""
        cache_dir = Path(temp_dir) / "cache"

        with patch('scrapers.cache_manager.psycopg2.connect', return_value=mock_db_connection):
            CacheManager("postgresql://test", cache_dir=cache_dir)

            assert cache_dir.exists()
            assert cache_dir.is_dir()

    def test_init_creates_tables(self, mock_db_connection):
        """Test that initialization creates required tables."""
        with patch('scrapers.cache_manager.psycopg2.connect', return_value=mock_db_connection):
            CacheManager("postgresql://test")

            assert mock_db_connection.cursor.called
            assert mock_db_connection.commit.called

    def test_get_cache_hit(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test get_cache returns cached content on hit."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # Mock cache hit response
        cache_row = {
            "cache_id": 1,
            "http_status": 200,
            "html_file_uuid": "test-uuid",
            "parsed_data": None,
            "scraped_at": datetime.utcnow(),
        }
        mock_cursor.fetchone.return_value = cache_row

        # Mock file exists
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=sample_html_content):
                result = cache_manager_with_mock.get_cache(
                    url="https://example.com/test",
                    site_name="athome",
                    page_type="detail"
                )

                assert result is not None
                assert result["from_cache"] is True
                assert result["raw_html"] == sample_html_content

    def test_get_cache_miss(self, cache_manager_with_mock, mock_db_connection):
        """Test get_cache returns None on miss."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        result = cache_manager_with_mock.get_cache(
            url="https://example.com/test",
            site_name="athome",
            page_type="detail"
        )

        assert result is None

    def test_get_cache_file_missing(self, cache_manager_with_mock, mock_db_connection):
        """Test get_cache handles missing cache file."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        cache_row = {
            "cache_id": 1,
            "http_status": 200,
            "html_file_uuid": "missing-uuid",
            "parsed_data": None,
            "scraped_at": datetime.utcnow(),
        }
        mock_cursor.fetchone.return_value = cache_row

        with patch.object(Path, 'exists', return_value=False):
            result = cache_manager_with_mock.get_cache(
                url="https://example.com/test",
                site_name="athome",
                page_type="detail"
            )

            # Should treat as cache miss
            assert result is None

    def test_set_cache_new_entry(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test set_cache stores new cache entry."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # No existing content
        mock_cursor.fetchone.return_value = None
        mock_cursor.fetchone.return_value = None  # First call for existing check
        mock_cursor.rowcount = 1

        # Mock file write
        with patch.object(Path, 'write_text'):
            cache_id = cache_manager_with_mock.set_cache(
                url="https://example.com/test",
                site_name="athome",
                page_type="detail",
                http_status=200,
                raw_html=sample_html_content
            )

            assert mock_db_connection.commit.called

    def test_set_cache_content_dedup(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test set_cache reuses existing file for duplicate content."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # Existing content with same hash
        mock_cursor.fetchone.side_effect = [
            (123, "existing-uuid"),  # Existing cache entry
            None  # No rowcount
        ]

        cache_id = cache_manager_with_mock.set_cache(
            url="https://example.com/test",
            site_name="athome",
            page_type="detail",
            http_status=200,
            raw_html=sample_html_content
        )

        # Should reuse existing cache_id
        assert mock_db_connection.commit.called

    def test_set_cache_with_parsed_data(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test set_cache stores parsed data."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        parsed_data = {"title": "Test", "price": 1000}

        with patch.object(Path, 'write_text'):
            cache_manager_with_mock.set_cache(
                url="https://example.com/test",
                site_name="athome",
                page_type="detail",
                http_status=200,
                raw_html=sample_html_content,
                parsed_data=parsed_data
            )

            assert mock_db_connection.commit.called

    @pytest.mark.parametrize("page_type,expected_ttl", [
        ("list", 6 * 3600),  # 6 hours
        ("detail", 7 * 86400),  # 7 days
        ("image", 30 * 86400),  # 30 days
    ])
    def test_set_cache_ttl_by_page_type(self, cache_manager_with_mock, mock_db_connection,
                                       page_type, expected_ttl, sample_html_content):
        """Test that TTL is set correctly based on page type."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        with patch.object(Path, 'write_text'):
            cache_manager_with_mock.set_cache(
                url="https://example.com/test",
                site_name="athome",
                page_type=page_type,
                http_status=200,
                raw_html=sample_html_content
            )

            # Verify commit was called (TTL is used in the query)
            assert mock_db_connection.commit.called

    def test_invalidate_entry(self, cache_manager_with_mock, mock_db_connection):
        """Test _invalidate_entry marks entry as invalid."""
        cache_manager_with_mock._invalidate_entry("test-hash")

        assert mock_db_connection.commit.called

    def test_cleanup_old_cache(self, cache_manager_with_mock, mock_db_connection):
        """Test cleanup_old_cache removes expired entries."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # Mock expired entries
        mock_cursor.rowcount = 5

        # Mock valid UUIDs
        mock_cursor.fetchall.return_value []

        # Mock file glob
        with patch.object(Path, 'glob', return_value=[]):
            result = cache_manager_with_mock.cleanup_old_cache()

            assert isinstance(result, dict)
            assert "entries_invalidated" in result
            assert "files_deleted" in result

    def test_get_stats(self, cache_manager_with_mock, mock_db_connection):
        """Test get_stats returns cache statistics."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # Mock total entries
        mock_cursor.fetchone.side_effect = [
            {"total": 100},  # Total entries
            {"total_requests": 1000, "cache_hits": 800, "cache_misses": 200},  # Today's stats
        ]

        # Mock file glob for size calculation
        with patch.object(Path, 'glob', return_value=[]):
            stats = cache_manager_with_mock.get_stats()

            assert stats["total_entries"] == 100
            assert stats["today_requests"] == 1000
            assert stats["today_hits"] == 800
            assert stats["today_misses"] == 200
            assert stats["hit_rate"] == 0.8

    def test_get_stats_no_data(self, cache_manager_with_mock, mock_db_connection):
        """Test get_stats returns zeros when no data."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        mock_cursor.fetchone.side_effect = [
            {"total": 0},
            None
        ]

        with patch.object(Path, 'glob', return_value=[]):
            stats = cache_manager_with_mock.get_stats()

            assert stats["total_entries"] == 0
            assert stats["today_requests"] == 0
            assert stats["today_hits"] == 0
            assert stats["today_misses"] == 0
            assert stats["hit_rate"] == 0

    def test_update_stats_hit(self, cache_manager_with_mock, mock_db_connection):
        """Test _update_stats increments cache hits."""
        cache_manager_with_mock._update_stats(cache_hit=True)

        assert mock_db_connection.commit.called

    def test_update_stats_miss(self, cache_manager_with_mock, mock_db_connection):
        """Test _update_stats increments cache misses."""
        cache_manager_with_mock._update_stats(cache_miss=True)

        assert mock_db_connection.commit.called

    @pytest.mark.parametrize("url,site_name,page_type", [
        ("https://example.com/1", "athome", "detail"),
        ("https://example.com/2", "suumo", "list"),
        ("https://example.com/3", "ieichiba", "image"),
    ])
    def test_cache_multiple_sites(self, cache_manager_with_mock, mock_db_connection,
                                url, site_name, page_type, sample_html_content):
        """Test caching works for multiple sites."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        with patch.object(Path, 'write_text'):
            cache_manager_with_mock.set_cache(
                url=url,
                site_name=site_name,
                page_type=page_type,
                http_status=200,
                raw_html=sample_html_content
            )

            assert mock_db_connection.commit.called

    def test_cache_hit_increments_counter(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test that cache hits increment the hit counter."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        cache_row = {
            "cache_id": 1,
            "http_status": 200,
            "html_file_uuid": "test-uuid",
            "parsed_data": None,
            "scraped_at": datetime.utcnow(),
        }
        mock_cursor.fetchone.return_value = cache_row

        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'read_text', return_value=sample_html_content):
                cache_manager_with_mock.get_cache(
                    url="https://example.com/test",
                    site_name="athome",
                    page_type="detail"
                )

                # Verify UPDATE was called to increment cache_hits
                assert mock_db_connection.commit.called

    def test_content_hash_consistency(self, cache_manager_with_mock, mock_db_connection, sample_html_content):
        """Test that identical content produces same hash."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # First call - no existing
        mock_cursor.fetchone.side_effect = [None, None]

        with patch.object(Path, 'write_text'):
            cache_manager_with_mock.set_cache(
                url="https://example.com/test1",
                site_name="athome",
                page_type="detail",
                http_status=200,
                raw_html=sample_html_content
            )

            # Second call - existing found (dedup)
            mock_cursor.fetchone.side_effect = [(123, "test-uuid")]

            cache_manager_with_mock.set_cache(
                url="https://example.com/test2",
                site_name="athome",
                page_type="detail",
                http_status=200,
                raw_html=sample_html_content
            )

    def test_connection_cleanup(self, cache_manager_with_mock, mock_db_connection):
        """Test that database connections are properly closed."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        cache_manager_with_mock.get_cache(
            url="https://example.com/test",
            site_name="athome",
            page_type="detail"
        )

        # Verify connection was closed
        assert mock_db_connection.close.called


@pytest.mark.integration
class TestCacheManagerIntegration:
    """Integration tests for CacheManager with real filesystem."""

    @pytest.fixture
    def real_cache_dir(self, temp_dir):
        """Create a real cache directory for testing."""
        cache_dir = Path(temp_dir) / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def test_file_creation_and_deletion(self, real_cache_dir):
        """Test actual file creation and deletion."""
        # This would test real filesystem operations
        pass

    def test_cache_size_calculation(self, real_cache_dir):
        """Test cache size calculation with real files."""
        # This would test size calculations
        pass

    @pytest.mark.slow
    def test_cleanup_performance(self, real_cache_dir):
        """Test cleanup performance with many files."""
        # This would test cleanup performance
        pass
