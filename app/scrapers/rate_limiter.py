"""Rate limiter for web scraping."""
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using SQLite for tracking requests."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure rate limit tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    limit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT UNIQUE NOT NULL,
                    max_requests INTEGER NOT NULL DEFAULT 60,
                    period_seconds INTEGER NOT NULL DEFAULT 300,
                    concurrent_limit INTEGER DEFAULT 1,
                    retry_after_seconds INTEGER DEFAULT 60,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_tracker (
                    tracker_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    request_timestamp TEXT NOT NULL,
                    response_time_ms INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
                    error_message TEXT,
                    from_cache BOOLEAN DEFAULT 0
                )
                """
            )
            conn.execute(
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
                conn.execute(
                    """
                    INSERT OR IGNORE INTO rate_limits (site_name, max_requests, period_seconds)
                    VALUES (?, ?, ?)
                    """,
                    (site_name, max_requests, period_seconds),
                )
            conn.commit()

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
        window_start = (datetime.utcnow() - timedelta(seconds=period_seconds)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                """
                SELECT COUNT(*) FROM rate_limit_tracker
                WHERE site_name = ?
                  AND request_timestamp >= ?
                  AND status = 'success'
                  AND from_cache = 0
                """,
                (site_name, window_start),
            ).fetchone()[0]

        if count >= max_requests:
            # Calculate wait time
            with sqlite3.connect(self.db_path) as conn:
                oldest = conn.execute(
                    """
                    SELECT request_timestamp FROM rate_limit_tracker
                    WHERE site_name = ?
                      AND request_timestamp >= ?
                      AND status = 'success'
                      AND from_cache = 0
                    ORDER BY request_timestamp ASC
                    LIMIT 1
                    """,
                    (site_name, window_start),
                ).fetchone()

            if oldest:
                oldest_time = datetime.fromisoformat(oldest[0])
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO rate_limit_tracker
                (site_name, request_timestamp, response_time_ms, status, error_message, from_cache)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    site_name,
                    datetime.utcnow().isoformat(),
                    response_time_ms,
                    status,
                    error_message,
                    from_cache,
                ),
            )
            conn.commit()

    def get_stats(self, site_name: str) -> Dict[str, any]:
        """Get rate limit statistics for a site."""
        config = self._get_config(site_name)
        if not config:
            return {}

        period_seconds = config["period_seconds"]
        window_start = (datetime.utcnow() - timedelta(seconds=period_seconds)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            # Count requests in current window
            stats = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'success' AND from_cache = 0) as successful,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE from_cache = 1) as cached,
                    AVG(response_time_ms) FILTER (WHERE response_time_ms IS NOT NULL) as avg_response_ms
                FROM rate_limit_tracker
                WHERE site_name = ?
                  AND request_timestamp >= ?
                """,
                (site_name, window_start),
            ).fetchone()

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
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM rate_limits WHERE site_name = ?", (site_name,)
            ).fetchone()
            return dict(row) if row else None
