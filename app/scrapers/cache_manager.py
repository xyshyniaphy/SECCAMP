"""Multi-layered cache manager: DB metadata + local HTML files (UUID-named)."""
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor

from .url_normalizer import URLNormalizer


logger = logging.getLogger(__name__)


class CacheManager:
    """
    Multi-layered cache manager for SECCAMP.

    Layer 1 (Neon PostgreSQL): Metadata, UUID references, TTL tracking
    Layer 2 (Local filesystem): HTML content stored as UUID files

    This design keeps Neon DB small (500MB limit) while storing
    actual HTML content locally with unlimited space.
    """

    # TTL values
    TTL_LIST_PAGE = 6 * 3600  # 6 hours
    TTL_DETAIL_PAGE = 7 * 86400  # 7 days
    TTL_IMAGE = 30 * 86400  # 30 days

    # Cache cleanup settings
    MAX_CACHE_SIZE_MB = 1000  # 1GB max local cache
    CLEANUP_AGE_DAYS = 30  # Auto-remove files older than 30 days

    def __init__(self, database_url: str, cache_dir: Optional[Path] = None):
        """
        Initialize cache manager.

        Args:
            database_url: PostgreSQL connection URL
            cache_dir: Directory for local HTML files (default: data/cache/html)
        """
        self.database_url = database_url
        self.cache_dir = cache_dir or Path("/data/cache/html")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
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
                # Create scraped_pages_cache table (metadata + UUID reference)
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scraped_pages_cache (
                        cache_id BIGSERIAL PRIMARY KEY,
                        http_status INTEGER NOT NULL,
                        http_headers JSONB,
                        html_file_uuid TEXT UNIQUE,
                        content_hash TEXT NOT NULL UNIQUE,
                        parsed_data JSONB,
                        scraper_version TEXT DEFAULT '1.0',
                        user_agent TEXT,
                        scraped_at TIMESTAMP NOT NULL,
                        scraping_duration_ms INTEGER,
                        parsing_success BOOLEAN DEFAULT TRUE,
                        parsing_error TEXT,
                        file_size_bytes INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                # Create cache_stats table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_stats (
                        stat_id SERIAL PRIMARY KEY,
                        stat_date DATE NOT NULL UNIQUE,
                        total_requests INTEGER DEFAULT 0,
                        cache_hits INTEGER DEFAULT 0,
                        cache_misses INTEGER DEFAULT 0,
                        cache_expired INTEGER DEFAULT 0,
                        cache_invalidated INTEGER DEFAULT 0,
                        bandwidth_saved_mb REAL DEFAULT 0,
                        time_saved_seconds REAL DEFAULT 0,
                        total_cache_entries INTEGER DEFAULT 0,
                        total_file_size_mb REAL DEFAULT 0,
                        entries_cleaned INTEGER DEFAULT 0,
                        files_cleaned INTEGER DEFAULT 0,
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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_cache_file_uuid ON scraped_pages_cache(html_file_uuid)"
                )
                conn.commit()
        finally:
            conn.close()

    def get_cache(
        self, url: str, site_name: str, page_type: str = "detail"
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached page with HTML from local file.

        Args:
            url: The URL to fetch
            site_name: The site name for normalization
            page_type: Type of page ('list', 'detail', 'image')

        Returns:
            Dict with raw_html (from file), parsed_data, from_cache or None if miss
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

        # Read HTML from local file
        html_file_uuid = row["html_file_uuid"]
        html_path = self.cache_dir / f"{html_file_uuid}.html"

        raw_html = None
        if html_path.exists():
            try:
                raw_html = html_path.read_text(encoding="utf-8")
                # Update file access time
                os.utime(html_path, None)
            except Exception as e:
                logger.warning(f"Failed to read cache file {html_path}: {e}")
                # File missing/corrupted - treat as cache miss
                self._update_stats(cache_miss=True)
                return None
        else:
            # File missing - invalidate cache entry
            logger.warning(f"Cache file missing: {html_path}")
            self._invalidate_entry(url_hash)
            self._update_stats(cache_miss=True)
            return None

        self._update_stats(cache_hit=True)
        logger.debug(f"Cache HIT: {url} (file: {html_file_uuid})")
        return {
            "cache_id": row["cache_id"],
            "url": url,
            "http_status": row["http_status"],
            "raw_html": raw_html,
            "parsed_data": row["parsed_data"],
            "scraped_at": row["scraped_at"],
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
        Store cache: metadata in DB, HTML as local UUID file.

        Args:
            url: The URL that was scraped
            site_name: The site name for normalization
            page_type: Type of page ('list', 'detail', 'image')
            http_status: HTTP status code
            raw_html: The HTML content (saved to local file)
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

        # Content hash for dedup
        content_hash = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
        html_size = len(raw_html.encode("utf-8"))

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Check if content hash exists (dedup)
                cur.execute(
                    "SELECT cache_id, html_file_uuid FROM scraped_pages_cache WHERE content_hash = %s",
                    (content_hash,),
                )
                existing = cur.fetchone()

                file_uuid = None

                if existing:
                    # Content already cached - reuse file
                    cache_id, file_uuid = existing
                    logger.debug(f"Content dedup: reusing existing cache file {file_uuid}")
                else:
                    # Create new cache file with UUID
                    file_uuid = str(uuid.uuid4())
                    html_path = self.cache_dir / f"{file_uuid}.html"

                    # Write HTML to file
                    html_path.write_text(raw_html, encoding="utf-8")
                    logger.debug(f"Saved HTML to cache file: {html_path} ({html_size} bytes)")

                    # Insert metadata into DB
                    cur.execute(
                        """
                        INSERT INTO scraped_pages_cache
                        (http_status, html_file_uuid, content_hash, parsed_data,
                         scraped_at, scraping_duration_ms, file_size_bytes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING cache_id
                        """,
                        (
                            http_status,
                            file_uuid,
                            content_hash,
                            json.dumps(parsed_data) if parsed_data else None,
                            now,
                            duration_ms,
                            html_size,
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

        logger.debug(f"Cache stored: {url} -> {file_uuid}")
        return cache_id

    def _invalidate_entry(self, url_hash: str) -> None:
        """Invalidate a cache entry when file is missing."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cache_entries SET is_valid = FALSE WHERE url_hash = %s",
                    (url_hash,),
                )
                conn.commit()
        finally:
            conn.close()

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

    def cleanup_old_cache(self) -> Dict[str, Any]:
        """
        Auto-cleanup old cache files and database entries.

        Removes:
        1. Expired cache entries
        2. Orphaned files (no DB reference)
        3. Files older than CLEANUP_AGE_DAYS
        4. Files if total size exceeds MAX_CACHE_SIZE_MB (LRU)

        Returns:
            Cleanup statistics
        """
        logger.info("Starting cache cleanup...")

        entries_invalidated = 0
        files_deleted = 0
        bytes_freed = 0

        conn = self._get_connection()
        try:
            # Step 1: Invalidate expired entries
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE cache_entries
                    SET is_valid = FALSE
                    WHERE expires_at < CURRENT_TIMESTAMP AND is_valid = TRUE
                    """
                )
                entries_invalidated = cur.rowcount
                conn.commit()

            # Step 2: Get all valid file_uuids from DB
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT html_file_uuid
                    FROM scraped_pages_cache spc
                    JOIN cache_entries ce ON spc.cache_id = ce.cache_id
                    WHERE ce.is_valid = TRUE AND spc.html_file_uuid IS NOT NULL
                    """
                )
                valid_uuids = {row[0] for row in cur.fetchall()}

            # Step 3: Find and delete orphaned files
            for html_file in self.cache_dir.glob("*.html"):
                file_uuid = html_file.stem

                # Check if file is orphaned (not in valid_uuids)
                if file_uuid not in valid_uuids:
                    file_size = html_file.stat().st_size
                    html_file.unlink()
                    files_deleted += 1
                    bytes_freed += file_size
                    logger.debug(f"Deleted orphaned cache file: {html_file}")

            # Step 4: Delete files older than CLEANUP_AGE_DAYS
            cutoff_time = datetime.utcnow() - timedelta(days=self.CLEANUP_AGE_DAYS)
            for html_file in self.cache_dir.glob("*.html"):
                file_uuid = html_file.stem

                # Skip files that are still valid
                if file_uuid in valid_uuids:
                    # Check file age
                    file_mtime = datetime.fromtimestamp(html_file.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        file_size = html_file.stat().st_size
                        html_file.unlink()
                        files_deleted += 1
                        bytes_freed += file_size

                        # Invalidate DB entry
                        cur.execute(
                            "UPDATE cache_entries SET is_valid = FALSE WHERE cache_id IN "
                            "(SELECT cache_id FROM scraped_pages_cache WHERE html_file_uuid = %s)",
                            (file_uuid,),
                        )
                        logger.debug(f"Deleted old cache file: {html_file}")

            conn.commit()

            # Step 5: LRU cleanup if size exceeds limit
            total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.html"))
            max_bytes = self.MAX_CACHE_SIZE_MB * 1024 * 1024

            if total_size > max_bytes:
                logger.info(f"Cache size ({total_size / 1024 / 1024:.1f} MB) exceeds limit ({self.MAX_CACHE_SIZE_MB} MB), running LRU cleanup...")

                # Get files sorted by last access time (from DB)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT spc.html_file_uuid, ce.last_accessed_at
                        FROM scraped_pages_cache spc
                        JOIN cache_entries ce ON spc.cache_id = ce.cache_id
                        WHERE ce.is_valid = TRUE AND spc.html_file_uuid IS NOT NULL
                        ORDER BY ce.last_accessed_at ASC
                        """
                    )
                    files_by_lru = cur.fetchall()

                current_size = total_size
                for file_uuid, last_accessed in files_by_lru:
                    if current_size <= max_bytes * 0.8:  # Target 80% of max
                        break

                    html_file = self.cache_dir / f"{file_uuid}.html"
                    if html_file.exists():
                        file_size = html_file.stat().st_size
                        html_file.unlink()
                        current_size -= file_size
                        files_deleted += 1
                        bytes_freed += file_size

                        # Invalidate DB entry
                        cur.execute(
                            "UPDATE cache_entries SET is_valid = FALSE WHERE cache_id IN "
                            "(SELECT cache_id FROM scraped_pages_cache WHERE html_file_uuid = %s)",
                            (file_uuid,),
                        )
                        logger.debug(f"LRU deleted: {file_uuid} (last accessed: {last_accessed})")

                conn.commit()

            # Step 6: Delete orphaned cache records (no file)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM cache_entries
                    WHERE is_valid = FALSE
                      AND cache_id IN (SELECT cache_id FROM scraped_pages_cache)
                    """
                )
                deleted_entries = cur.rowcount

                cur.execute(
                    """
                    DELETE FROM scraped_pages_cache
                    WHERE cache_id NOT IN (SELECT DISTINCT cache_id FROM cache_entries WHERE is_valid = TRUE)
                    """
                )
                conn.commit()

            # Update stats
            today = date.today()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cache_stats (stat_date, entries_cleaned, files_cleaned)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (stat_date) DO UPDATE SET
                        entries_cleaned = cache_stats.entries_cleaned + EXCLUDED.entries_cleaned,
                        files_cleaned = cache_stats.files_cleaned + EXCLUDED.files_cleaned
                    """,
                    (today, entries_invalidated, files_deleted),
                )
                conn.commit()

        finally:
            conn.close()

        logger.info(f"Cache cleanup complete: entries_invalidated={entries_invalidated}, "
                   f"files_deleted={files_deleted}, bytes_freed={bytes_freed / 1024 / 1024:.1f} MB")

        return {
            "entries_invalidated": entries_invalidated,
            "files_deleted": files_deleted,
            "bytes_freed": bytes_freed,
        }

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

                # Total file size
                total_file_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.html"))

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
            "total_file_size_mb": round(total_file_size / 1024 / 1024, 2),
            "cache_dir": str(self.cache_dir),
            "today_requests": stats["total_requests"] if stats else 0,
            "today_hits": stats["cache_hits"] if stats else 0,
            "today_misses": stats["cache_misses"] if stats else 0,
            "hit_rate": (
                stats["cache_hits"] / stats["total_requests"]
                if stats and stats["total_requests"] > 0
                else 0
            ),
        }
