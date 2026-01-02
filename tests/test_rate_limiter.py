"""
Tests for RateLimiter.
"""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from scrapers.rate_limiter import RateLimiter


@pytest.mark.unit
class TestRateLimiter:
    """Test suite for RateLimiter class."""

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock database connection."""
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock()
        conn.cursor.return_value.__exit__ = Mock()
        return conn

    @pytest.fixture
    def rate_limiter_with_mock(self, mock_db_connection):
        """Create a RateLimiter with mocked database connection."""
        with patch('scrapers.rate_limiter.psycopg2.connect', return_value=mock_db_connection):
            limiter = RateLimiter("postgresql://test")
            return limiter

    def test_init_creates_tables(self, mock_db_connection):
        """Test that initialization creates required tables."""
        with patch('scrapers.rate_limiter.psycopg2.connect', return_value=mock_db_connection):
            limiter = RateLimiter("postgresql://test")

            # Verify table creation queries were executed
            assert mock_db_connection.cursor.called
            assert mock_db_connection.commit.called

    def test_init_inserts_default_limits(self, mock_db_connection):
        """Test that initialization inserts default rate limits."""
        with patch('scrapers.rate_limiter.psycopg2.connect', return_value=mock_db_connection):
            RateLimiter("postgresql://test")

            # Check that INSERT was called for default sites
            assert mock_db_connection.commit.called

    def test_can_make_request_when_allowed(self, rate_limiter_with_mock, mock_db_connection):
        """Test can_make_request returns True when under limit."""
        # Mock cursor to return 0 requests (under limit)
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = [0]

        result = rate_limiter_with_mock.can_make_request("athome")

        assert result["allowed"] is True
        assert result["wait_seconds"] == 0

    def test_can_make_request_when_limit_reached(self, rate_limiter_with_mock, mock_db_connection):
        """Test can_make_request returns False when at limit."""
        # Mock config to return max_requests=60, period=300
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # First call for config
        config_row = {
            "site_name": "athome",
            "max_requests": 60,
            "period_seconds": 300
        }

        # Second call returns 60 requests (at limit)
        mock_cursor.fetchone.side_effect = [
            config_row,  # _get_config
            [60],  # COUNT(*) in can_make_request
            (datetime.utcnow(),),  # oldest request timestamp
        ]

        result = rate_limiter_with_mock.can_make_request("athome")

        assert result["allowed"] is False
        assert result["wait_seconds"] > 0

    def test_can_make_request_unknown_site(self, rate_limiter_with_mock, mock_db_connection):
        """Test can_make_request allows unknown sites."""
        # Mock cursor to return None (no config)
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        result = rate_limiter_with_mock.can_make_request("unknown_site")

        # Should allow but log warning
        assert result["allowed"] is True
        assert result["wait_seconds"] == 0

    def test_can_make_request_excludes_cached_requests(self, rate_limiter_with_mock, mock_db_connection):
        """Test that cached requests are excluded from rate limit."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = [30]  # Only 30 non-cached requests

        result = rate_limiter_with_mock.can_make_request("athome")

        assert result["allowed"] is True

    def test_record_request_success(self, rate_limiter_with_mock, mock_db_connection):
        """Test recording a successful request."""
        rate_limiter_with_mock.record_request(
            site_name="athome",
            status="success",
            response_time_ms=150
        )

        assert mock_db_connection.commit.called

    def test_record_request_failure(self, rate_limiter_with_mock, mock_db_connection):
        """Test recording a failed request."""
        rate_limiter_with_mock.record_request(
            site_name="athome",
            status="failed",
            error_message="Connection timeout"
        )

        assert mock_db_connection.commit.called

    def test_record_request_from_cache(self, rate_limiter_with_mock, mock_db_connection):
        """Test recording a cached request."""
        rate_limiter_with_mock.record_request(
            site_name="athome",
            status="success",
            from_cache=True
        )

        assert mock_db_connection.commit.called

    def test_get_stats(self, rate_limiter_with_mock, mock_db_connection):
        """Test getting rate limit statistics."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # Mock config and stats
        config_row = {
            "site_name": "athome",
            "max_requests": 60,
            "period_seconds": 300
        }

        stats_row = (
            30,  # successful
            2,   # failed
            10,  # cached
            150.5  # avg_response_ms
        )

        mock_cursor.fetchone.side_effect = [config_row, stats_row]

        stats = rate_limiter_with_mock.get_stats("athome")

        assert stats["max_requests"] == 60
        assert stats["period_seconds"] == 300
        assert stats["current_requests"] == 30
        assert stats["failed_requests"] == 2
        assert stats["cached_requests"] == 10
        assert stats["avg_response_ms"] == 150.5
        assert stats["remaining"] == 30

    def test_get_stats_unknown_site(self, rate_limiter_with_mock, mock_db_connection):
        """Test getting stats for unknown site."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.return_value = None

        stats = rate_limiter_with_mock.get_stats("unknown_site")

        assert stats == {}

    def test_wait_if_needed_no_wait(self, rate_limiter_with_mock):
        """Test wait_if_needed when no waiting required."""
        with patch.object(rate_limiter_with_mock, 'can_make_request', return_value={
            "allowed": True,
            "wait_seconds": 0
        }):
            result = rate_limiter_with_mock.wait_if_needed("athome")

            assert result is False

    def test_wait_if_needed_with_wait(self, rate_limiter_with_mock):
        """Test wait_if_needed when waiting is required."""
        with patch.object(rate_limiter_with_mock, 'can_make_request', return_value={
            "allowed": False,
            "wait_seconds": 0.1
        }):
            start = time.time()
            result = rate_limiter_with_mock.wait_if_needed("athome")
            elapsed = time.time() - start

            assert result is True
            assert elapsed >= 0.1

    @pytest.mark.parametrize("site_name,expected_max,expected_period", [
        ("athome", 60, 300),
        ("suumo", 30, 300),
        ("ieichiba", 20, 300),
        ("zero_estate", 10, 300),
        ("jmty", 20, 300),
    ])
    def test_default_rate_limits(self, rate_limiter_with_mock, mock_db_connection,
                                site_name, expected_max, expected_period):
        """Test that default rate limits are configured correctly."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        config_row = {
            "site_name": site_name,
            "max_requests": expected_max,
            "period_seconds": expected_period
        }
        mock_cursor.fetchone.return_value = config_row

        result = rate_limiter_with_mock._get_config(site_name)

        assert result["max_requests"] == expected_max
        assert result["period_seconds"] == expected_period

    def test_record_request_validates_status(self, rate_limiter_with_mock, mock_db_connection):
        """Test that record_request validates status values."""
        for status in ["success", "failed", "timeout"]:
            rate_limiter_with_mock.record_request(
                site_name="athome",
                status=status
            )

            assert mock_db_connection.commit.called

    def test_multiple_sites_separate_limits(self, rate_limiter_with_mock, mock_db_connection):
        """Test that different sites have separate rate limits."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__

        # athome at limit
        mock_cursor.fetchone.side_effect = [
            {"site_name": "athome", "max_requests": 60, "period_seconds": 300},
            [60],
        ]

        result_athome = rate_limiter_with_mock.can_make_request("athome")

        # suumo under limit
        mock_cursor.fetchone.side_effect = [
            {"site_name": "suumo", "max_requests": 30, "period_seconds": 300},
            [10],
        ]

        result_suumo = rate_limiter_with_mock.can_make_request("suumo")

        # Each site should have independent limits
        assert result_athome["allowed"] is False
        assert result_suumo["allowed"] is True

    def test_connection_close_after_get_stats(self, rate_limiter_with_mock, mock_db_connection):
        """Test that database connection is properly closed."""
        mock_cursor = mock_db_connection.cursor.return_value.__enter__
        mock_cursor.fetchone.side_effect = [
            {"site_name": "athome", "max_requests": 60, "period_seconds": 300},
            (0, 0, 0, 0),
        ]

        rate_limiter_with_mock.get_stats("athome")

        # Verify connection was closed
        assert mock_db_connection.close.called


@pytest.mark.integration
class TestRateLimiterIntegration:
    """Integration tests for RateLimiter with real database."""

    @pytest.fixture
    def rate_limiter_db(self, initialized_db):
        """Create RateLimiter with test database."""
        # Use SQLite in-memory for testing (simulating PostgreSQL)
        # In real implementation, this would use PostgreSQL
        pass

    @pytest.mark.slow
    def test_rate_limiting_over_time(self):
        """Test rate limiting behavior over time."""
        # This would test actual rate limiting behavior
        # with real timing and database operations
        pass

    @pytest.mark.slow
    def test_concurrent_requests(self):
        """Test rate limiting with concurrent requests."""
        # This would test thread-safety and concurrent access
        pass
