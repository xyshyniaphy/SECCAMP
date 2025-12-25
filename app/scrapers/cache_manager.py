"""Cache manager for scraped pages (Neon PostgreSQL)."""
import hashlib
import json
import logging
import zlib
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import text

from .url_normalizer import URLNormalizer


logger = logging.getLogger(__name__)


class CacheManager:
    """Manage page cache with TTL and compression using Neon PostgreSQL."""

    # TTL values
    TTL_LIST_PAGE = 6 * 3600  # 6 hours
    TTL_DETAIL_PAGE = 7 * 86400  # 7 days
    TTL_IMAGE = 30 * 86400  # 30 days

    def __init__(self, database_url: str):
        """
        Initialize cache manager.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self._ensure_tables()

    def _get_connection(self):
        """Get PostgreSQL connection."""
        return psycopg2.connect(self.database_url)

    def _ensure_tables(self) -> None:
        """Ensure cache tables exist."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Create cache_entries table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_entries (
                        entry_id BIGSERIAL PRIMARY KEY,
                        original_url TEXT NOT NULL,
                        normalized_url TEXT NOT NULL UNIQUE,
                        url_hash TEXT NOT NULL UNIQUE,
                        source_site TEXT NOT NULL,
                        page_type TEXT NOT NULL CHECK(page_type IN ('list', 'detail', 'image')),
                        is_valid BOOLEAN DEFAULT TRUE,
                        cache_hits INTEGER DEFAULT 0,
                        first_cached_at TIMESTAMP NOT NULL,
                        last_accessed_at TIMESTAMP NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        cache_id BIGINT,
                        FOREIGN KEY (cache_id) REFERENCES scraped_pages_cache(cache_id) ON DELETE CASCADE
                    )
                    """
                )
                # Create scraped_pages_cache table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scraped_pages_cache (
                        cache_id BIGSERIAL PRIMARY KEY,
                        http_status INTEGER NOT NULL,
                        http_headers JSONB,
                        raw_html TEXT,
                        raw_html_size INTEGER,
                        is_compressed BOOLEAN DEFAULT FALSE,
                        parsed_data JSONB,
                        content_hash TEXT NOT NULL,
                        scraper_version TEXT DEFAULT '1.0',
                        user_agent TEXT,
                        scraped_at TIMESTAMP NOT NULL,
                        scraping_duration_ms INTEGER,
                        parsing_success BOOLEAN DEFAULT TRUE,
                        parsing_error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                # Create indexes
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cache_url_hash ON cache_entries(url_hash)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cache_content_hash ON scraped_pages_cache(content_hash)"
                )
                conn.commit()
        finally:
            conn.close()

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

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ce.*, spc.*
                    FROM cache_entries ce
                    JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
                    WHERE ce.url_hash = %s
                      AND ce.is_valid = TRUE
                      AND ce.expires_at > CURRENT_TIMESTAMP
                    """,
                    (url_hash,),
                )
                row = cur.fetchone()

                if not row:
                    self._update_stats(cache_miss=True)
                    return None

                # Update access stats
                cur.execute(
                    """
                    UPDATE cache_entries
                    SET cache_hits = cache_hits + 1,
                        last_accessed_at = CURRENT_TIMESTAMP
                    WHERE url_hash = %s
                    """,
                    (url_hash,),
                )
                conn.commit()

        finally:
            conn.close()

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

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl)

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

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Check if content exists (dedup)
                cur.execute(
                    "SELECT cache_id FROM scraped_pages_cache WHERE content_hash = %s",
                    (content_hash,),
                )
                existing = cur.fetchone()

                if existing:
                    cache_id = existing[0]
                else:
                    # Insert new cache content
                    cur.execute(
                        """
                        INSERT INTO scraped_pages_cache
                        (http_status, raw_html, raw_html_size, is_compressed,
                         parsed_data, content_hash, scraped_at, scraping_duration_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING cache_id
                        """,
                        (
                            http_status,
                            raw_html,
                            html_size,
                            is_compressed,
                            json.dumps(parsed_data) if parsed_data else None,
                            content_hash,
                            now,
                            duration_ms,
                        ),
                    )
                    cache_id = cur.fetchone()[0]

                # Insert or update entry
                cur.execute(
                    """
                    INSERT INTO cache_entries
                    (original_url, normalized_url, url_hash, source_site, page_type,
                     first_cached_at, last_accessed_at, expires_at, cache_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url_hash) DO UPDATE SET
                        cache_id = EXCLUDED.cache_id,
                        expires_at = EXCLUDED.expires_at,
                        last_accessed_at = EXCLUDED.last_accessed_at,
                        is_valid = TRUE
                    """,
                    (
                        norm["original_url"],
                        norm["normalized_url"],
                        norm["url_hash"],
                        site_name,
                        page_type,
                        now,
                        now,
                        expires_at,
                        cache_id,
                    ),
                )

                conn.commit()

        finally:
            conn.close()

        logger.debug(f"Cached: {url}")
        return cache_id

    def _update_stats(self, cache_hit: bool = False, cache_miss: bool = False) -> None:
        """Update daily cache statistics."""
        today = date.today()

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cache_stats (stat_date, total_requests, cache_hits, cache_misses)
                    VALUES (%s, 1, %s, %s)
                    ON CONFLICT (stat_date) DO UPDATE SET
                        total_requests = cache_stats.total_requests + 1,
                        cache_hits = cache_stats.cache_hits + EXCLUDED.cache_hits,
                        cache_misses = cache_stats.cache_misses + EXCLUDED.cache_misses
                    """,
                    (today, 1 if cache_hit else 0, 1 if cache_miss else 0),
                )
                conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total valid entries
                cur.execute(
                    "SELECT COUNT(*) as total FROM cache_entries WHERE is_valid = TRUE"
                )
                total = cur.fetchone()["total"]

                # Total size
                cur.execute(
                    """
                    SELECT COALESCE(SUM(spc.raw_html_size) / 1024.0 / 1024.0, 0) as size
                    FROM cache_entries ce
                    JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
                    WHERE ce.is_valid = TRUE
                    """
                )
                size = cur.fetchone()["size"]

                # Today's stats
                today = date.today()
                cur.execute(
                    """
                    SELECT total_requests, cache_hits, cache_misses
                    FROM cache_stats
                    WHERE stat_date = %s
                    """,
                    (today,),
                )
                stats = cur.fetchone()

        finally:
            conn.close()

        return {
            "total_entries": total,
            "total_size_mb": round(size, 2),
            "today_requests": stats["total_requests"] if stats else 0,
            "today_hits": stats["cache_hits"] if stats else 0,
            "today_misses": stats["cache_misses"] if stats else 0,
            "hit_rate": (
                stats["cache_hits"] / stats["total_requests"]
                if stats and stats["total_requests"] > 0
                else 0
            ),
        }
