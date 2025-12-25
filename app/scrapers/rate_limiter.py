"""Rate limiter for web scraping (Neon PostgreSQL)."""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using Neon PostgreSQL for tracking requests."""

    def __init__(self, database_url: str):
        """
        Initialize rate limiter.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self._ensure_tables()

    def _get_connection(self):
        """Get PostgreSQL connection."""
        return psycopg2.connect(self.database_url)

    def _ensure_tables(self) -> None:
        """Ensure rate limit tables exist."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Create rate_limits table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        limit_id SERIAL PRIMARY KEY,
                        site_name TEXT UNIQUE NOT NULL,
                        max_requests INTEGER NOT NULL DEFAULT 60,
                        period_seconds INTEGER NOT NULL DEFAULT 300,
                        concurrent_limit INTEGER DEFAULT 1,
                        retry_after_seconds INTEGER DEFAULT 60,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                # Create rate_limit_tracker table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_limit_tracker (
                        tracker_id BIGSERIAL PRIMARY KEY,
                        site_name TEXT NOT NULL,
                        request_timestamp TIMESTAMP NOT NULL,
                        response_time_ms INTEGER,
                        status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
                        error_message TEXT,
                        from_cache BOOLEAN DEFAULT FALSE
                    )
                    """
                )
                # Create index
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tracker_site_time ON rate_limit_tracker(site_name, request_timestamp DESC)"
                )

                # Insert default limits if not exist
                defaults = [
                    ("athome", 60, 300),
                    ("suumo", 30, 300),
                    ("ieichiba", 20, 300),
                    ("zero_estate", 10, 300),
                    ("jmty", 20, 300),
                    ("homes", 30, 300),
                    ("rakuten", 30, 300),
                ]
                for site_name, max_requests, period_seconds in defaults:
                    cur.execute(
                        """
                        INSERT INTO rate_limits (site_name, max_requests, period_seconds)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (site_name) DO NOTHING
                        """,
                        (site_name, max_requests, period_seconds),
                    )
                conn.commit()
        finally:
            conn.close()

    def can_make_request(self, site_name: str) -> Dict[str, any]:
        """
        Check if a request can be made for the site.

        Args:
            site_name: The site to check

        Returns:
            Dict with 'allowed' (bool) and 'wait_seconds' (float)
        """
        # Get config
        config = self._get_config(site_name)
        if not config:
            logger.warning(f"No rate limit config for {site_name}, allowing")
            return {"allowed": True, "wait_seconds": 0}

        max_requests = config["max_requests"]
        period_seconds = config["period_seconds"]

        # Count successful requests in window
        window_start = datetime.utcnow() - timedelta(seconds=period_seconds)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM rate_limit_tracker
                    WHERE site_name = %s
                      AND request_timestamp >= %s
                      AND status = 'success'
                      AND from_cache = FALSE
                    """,
                    (site_name, window_start),
                )
                count = cur.fetchone()[0]

        finally:
            conn.close()

        if count >= max_requests:
            # Calculate wait time
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT request_timestamp FROM rate_limit_tracker
                        WHERE site_name = %s
                          AND request_timestamp >= %s
                          AND status = 'success'
                          AND from_cache = FALSE
                        ORDER BY request_timestamp ASC
                        LIMIT 1
                        """,
                        (site_name, window_start),
                    )
                    oldest = cur.fetchone()

            finally:
                conn.close()

            if oldest:
                oldest_time = oldest[0]
                expire_time = oldest_time + timedelta(seconds=period_seconds)
                wait_seconds = (expire_time - datetime.utcnow()).total_seconds()
                if wait_seconds > 0:
                    return {"allowed": False, "wait_seconds": wait_seconds}

        return {"allowed": True, "wait_seconds": 0}

    def wait_if_needed(self, site_name: str) -> bool:
        """
        Wait if rate limit is reached.

        Args:
            site_name: The site to check

        Returns:
            True if waited, False otherwise
        """
        check = self.can_make_request(site_name)

        if not check["allowed"]:
            wait_time = check["wait_seconds"]
            logger.warning(f"Rate limit reached for {site_name}. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            return True

        return False

    def record_request(
        self,
        site_name: str,
        status: str,
        response_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        from_cache: bool = False,
    ) -> None:
        """
        Record a request in the tracker.

        Args:
            site_name: The site name
            status: Request status ('success', 'failed', 'timeout')
            response_time_ms: Response time in milliseconds
            error_message: Error message if failed
            from_cache: Whether response was from cache
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rate_limit_tracker
                    (site_name, request_timestamp, response_time_ms, status, error_message, from_cache)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        site_name,
                        datetime.utcnow(),
                        response_time_ms,
                        status,
                        error_message,
                        from_cache,
                    ),
                )
                conn.commit()
        finally:
            conn.close()

    def get_stats(self, site_name: str) -> Dict[str, any]:
        """Get rate limit statistics for a site."""
        config = self._get_config(site_name)
        if not config:
            return {}

        period_seconds = config["period_seconds"]
        window_start = datetime.utcnow() - timedelta(seconds=period_seconds)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Count requests in current window
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'success' AND from_cache = FALSE) as successful,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed,
                        COUNT(*) FILTER (WHERE from_cache = TRUE) as cached,
                        AVG(response_time_ms) FILTER (WHERE response_time_ms IS NOT NULL) as avg_response_ms
                    FROM rate_limit_tracker
                    WHERE site_name = %s
                      AND request_timestamp >= %s
                    """,
                    (site_name, window_start),
                )
                stats = cur.fetchone()

        finally:
            conn.close()

        return {
            "max_requests": config["max_requests"],
            "period_seconds": period_seconds,
            "current_requests": stats[0] or 0,
            "failed_requests": stats[1] or 0,
            "cached_requests": stats[2] or 0,
            "avg_response_ms": round(stats[3] or 0, 1),
            "remaining": max(0, config["max_requests"] - (stats[0] or 0)),
        }

    def _get_config(self, site_name: str) -> Optional[Dict]:
        """Get rate limit config for a site."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM rate_limits WHERE site_name = %s", (site_name,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()
