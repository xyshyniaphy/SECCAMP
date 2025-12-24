"""Cache manager for scraped pages."""
import hashlib
import logging
import sqlite3
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from .url_normalizer import URLNormalizer


logger = logging.getLogger(__name__)

# SQLite connection timeout (seconds)
SQLITE_TIMEOUT = 30.0


class CacheManager:
    """Manage page cache with TTL and compression."""

    # TTL values
    TTL_LIST_PAGE = 6 * 3600  # 6 hours
    TTL_DETAIL_PAGE = 7 * 86400  # 7 days
    TTL_IMAGE = 30 * 86400  # 30 days

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a connection with timeout and WAL mode enabled."""
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT)
        conn.execute("PRAGMA busy_timeout=30000")
        # WAL mode is enabled by DatabaseManager, skip here to avoid lock
        return conn

    def _ensure_tables(self) -> None:
        """Ensure cache tables exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL UNIQUE,
                    url_hash TEXT NOT NULL UNIQUE,
                    source_site TEXT NOT NULL,
                    page_type TEXT NOT NULL CHECK(page_type IN ('list', 'detail', 'image')),
                    is_valid BOOLEAN DEFAULT 1,
                    cache_hits INTEGER DEFAULT 0,
                    first_cached_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    cache_id INTEGER,
                    FOREIGN KEY (cache_id) REFERENCES scraped_pages_cache(cache_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scraped_pages_cache (
                    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    http_status INTEGER NOT NULL,
                    http_headers TEXT,
                    raw_html TEXT,
                    raw_html_size INTEGER,
                    is_compressed BOOLEAN DEFAULT 0,
                    parsed_data TEXT,
                    content_hash TEXT NOT NULL,
                    scraper_version TEXT DEFAULT '1.0',
                    user_agent TEXT,
                    scraped_at TEXT NOT NULL,
                    scraping_duration_ms INTEGER,
                    parsing_success BOOLEAN DEFAULT 1,
                    parsing_error TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_url_hash ON cache_entries(url_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_content_hash ON scraped_pages_cache(content_hash)"
            )
            conn.commit()

    def get_cache(
        self, url: str, site_name: str, page_type: str = "detail"
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached page if available and not expired.

        Args:
            url: The URL to fetch
            site_name: The site name for normalization
            page_type: Type of page ('list', 'detail', 'image')

        Returns:
            Dict with raw_html, parsed_data, from_cache or None if miss
        """
        norm = URLNormalizer.normalize(url, site_name)
        url_hash = norm["url_hash"]

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row

            row = conn.execute(
                """
                SELECT ce.*, spc.*
                FROM cache_entries ce
                JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
                WHERE ce.url_hash = ?
                  AND ce.is_valid = 1
                  AND ce.expires_at > datetime('now')
                """,
                (url_hash,),
            ).fetchone()

            if not row:
                self._update_stats(cache_miss=True)
                return None

            # Update stats
            conn.execute(
                """
                UPDATE cache_entries
                SET cache_hits = cache_hits + 1,
                    last_accessed_at = datetime('now')
                WHERE url_hash = ?
                """,
                (url_hash,),
            )
            conn.commit()

        # Decompress if needed
        html = row["raw_html"]
        if row["is_compressed"]:
            html = zlib.decompress(html.encode("latin1")).decode("utf-8")

        self._update_stats(cache_hit=True)
        logger.debug(f"Cache HIT: {url}")
        return {
            "raw_html": html,
            "parsed_data": row["parsed_data"],
            "from_cache": True,
        }

    def set_cache(
        self,
        url: str,
        site_name: str,
        page_type: str,
        http_status: int,
        raw_html: str,
        parsed_data: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> int:
        """
        Store page in cache.

        Args:
            url: The URL that was scraped
            site_name: The site name for normalization
            page_type: Type of page ('list', 'detail', 'image')
            http_status: HTTP status code
            raw_html: The HTML content
            parsed_data: Optional parsed data as JSON string
            duration_ms: Optional scraping duration

        Returns:
            cache_id
        """
        norm = URLNormalizer.normalize(url, site_name)

        # Get TTL
        ttl = {
            "list": self.TTL_LIST_PAGE,
            "detail": self.TTL_DETAIL_PAGE,
            "image": self.TTL_IMAGE,
        }.get(page_type, self.TTL_DETAIL_PAGE)

        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        # Compress if large
        html_size = len(raw_html.encode("utf-8"))
        is_compressed = False
        if html_size > 10240:  # 10KB
            compressed = zlib.compress(raw_html.encode("utf-8"))
            if len(compressed) < html_size * 0.8:
                raw_html = compressed.decode("latin1")
                is_compressed = True

        # Content hash for dedup
        content_hash = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()

        with self._get_connection() as conn:
            # Check if content exists (dedup)
            existing = conn.execute(
                "SELECT cache_id FROM scraped_pages_cache WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()

            if existing:
                cache_id = existing[0]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO scraped_pages_cache
                    (http_status, raw_html, raw_html_size, is_compressed,
                     parsed_data, content_hash, scraped_at, scraping_duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        http_status,
                        raw_html,
                        html_size,
                        is_compressed,
                        parsed_data,
                        content_hash,
                        datetime.utcnow().isoformat(),
                        duration_ms,
                    ),
                )
                cache_id = cursor.lastrowid

            # Insert or update entry
            now = datetime.utcnow().isoformat()
            try:
                conn.execute(
                    """
                    INSERT INTO cache_entries
                    (original_url, normalized_url, url_hash, source_site, page_type,
                     first_cached_at, last_accessed_at, expires_at, cache_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        norm["original_url"],
                        norm["normalized_url"],
                        norm["url_hash"],
                        site_name,
                        page_type,
                        now,
                        now,
                        expires_at.isoformat(),
                        cache_id,
                    ),
                )
            except sqlite3.IntegrityError:
                # URL already exists, update
                conn.execute(
                    """
                    UPDATE cache_entries
                    SET cache_id = ?,
                        expires_at = ?,
                        last_accessed_at = ?,
                        is_valid = 1
                    WHERE url_hash = ?
                    """,
                    (cache_id, expires_at.isoformat(), now, norm["url_hash"]),
                )

            conn.commit()

        logger.debug(f"Cached: {url}")
        return cache_id

    def _update_stats(self, cache_hit: bool = False, cache_miss: bool = False) -> None:
        """Update daily cache statistics."""
        from datetime import date
        today = date.today().isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cache_stats (stat_date, total_requests, cache_hits, cache_misses)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(stat_date) DO UPDATE SET
                    total_requests = total_requests + 1,
                    cache_hits = cache_hits + excluded.cache_hits,
                    cache_misses = cache_misses + excluded.cache_misses
                """,
                (today, 1 if cache_hit else 0, 1 if cache_miss else 0),
            )
            conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row

            # Total valid entries
            total = conn.execute(
                "SELECT COUNT(*) FROM cache_entries WHERE is_valid = 1"
            ).fetchone()[0]

            # Total size
            size = conn.execute(
                """
                SELECT SUM(spc.raw_html_size) / 1024 / 1024
                FROM cache_entries ce
                JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
                WHERE ce.is_valid = 1
                """
            ).fetchone()[0] or 0

            # Today's stats
            from datetime import date
            today = date.today().isoformat()
            stats = conn.execute(
                """
                SELECT total_requests, cache_hits, cache_misses
                FROM cache_stats
                WHERE stat_date = ?
                """,
                (today,),
            ).fetchone()

        return {
            "total_entries": total,
            "total_size_mb": round(size, 2),
            "today_requests": stats[0] if stats else 0,
            "today_hits": stats[1] if stats else 0,
            "today_misses": stats[2] if stats else 0,
            "hit_rate": (
                stats[1] / stats[0] if stats and stats[0] > 0 else 0
            ),
        }
