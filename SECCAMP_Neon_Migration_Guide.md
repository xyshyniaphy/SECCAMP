# SECCAMP Migration to Neon PostgreSQL

**Version:** 6.0  
**Date:** 2025年12月25日 08:51 JST  
**Migration:** SQLite → Neon PostgreSQL (Serverless)

---

## Table of Contents

1. [Why Neon PostgreSQL?](#why-neon-postgresql)
2. [Neon Setup](#neon-setup)
3. [Schema Conversion](#schema-conversion)
4. [Connection Configuration](#connection-configuration)
5. [Code Migration](#code-migration)
6. [Data Migration](#data-migration)
7. [GitHub Actions Update](#github-actions-update)
8. [Testing](#testing)

---

## Why Neon PostgreSQL?

### Problems with SQLite in GitHub Actions

❌ **Ephemeral Storage** - Database lost after each run  
❌ **Git Tracking Issues** - Large binary files in Git  
❌ **No Concurrent Access** - File locking issues  
❌ **Limited Scalability** - Single file limitations  

### Benefits of Neon

✅ **Persistent Storage** - Database survives across runs  
✅ **Serverless** - Auto-scales, auto-suspends (free plan)  
✅ **PostgreSQL** - Full SQL features, better performance  
✅ **Free Tier** - 0.5 GB storage, 1 compute unit  
✅ **Branching** - Database branches like Git  
✅ **No Maintenance** - Fully managed  

### Neon Free Plan Limits

| Resource | Limit | SECCAMP Usage |
|----------|-------|---------------|
| Storage | 0.5 GB | ~100-200 MB (sufficient) |
| Compute | 1 unit | Enough for daily batch |
| Active time | Always available | Perfect |
| Branches | 1 | 1 (main) |
| Projects | 1 | 1 |
| Connection pooling | Yes | Built-in |

**Verdict:** ✅ Neon Free Plan is perfect for SECCAMP!

---

## Neon Setup

### Step 1: Create Neon Account

1. Go to https://neon.tech
2. Sign up with GitHub account (recommended)
3. Verify email

### Step 2: Create Project

```
Project Name: seccamp
Region: AWS ap-northeast-1 (Tokyo) ← Closest to you
PostgreSQL Version: 16 (latest)
```

### Step 3: Get Connection String

After project creation, you'll see:

```
Connection String:
postgresql://[user]:[password]@[host]/[database]?sslmode=require

Example:
postgresql://seccamp_owner:AbCdEf123@ep-blue-sky-12345.ap-northeast-1.aws.neon.tech/seccamp?sslmode=require
```

**⚠️ Save this immediately! Password shown only once.**

### Step 4: Connection String Breakdown

```
postgresql://[user]:[password]@[host]/[database]?sslmode=require
             │      │            │       │
             │      │            │       └─ Database name
             │      │            └───────── Neon host (unique)
             │      └────────────────────── Password (random)
             └───────────────────────────── Username
```

---

## Schema Conversion

### SQLite → PostgreSQL Differences

| Feature | SQLite | PostgreSQL | Change Needed |
|---------|--------|------------|---------------|
| Auto increment | INTEGER PRIMARY KEY AUTOINCREMENT | SERIAL or BIGSERIAL | ✅ Change |
| Boolean | INTEGER (0/1) | BOOLEAN | ✅ Change |
| DateTime | TEXT (ISO format) | TIMESTAMP | ✅ Change |
| JSON | TEXT | JSONB | ✅ Change |
| UNIQUE constraint | Table-level | Same | ✅ OK |
| CHECK constraint | Same | Same | ✅ OK |
| Indexes | Same syntax | Same | ✅ OK |

### Complete PostgreSQL Schema

```sql
-- ============================================
-- SECCAMP PostgreSQL Schema for Neon
-- Version 6.0 - Neon Migration
-- ============================================

-- Enable UUID extension (optional, for future use)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. RATE LIMITING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS rate_limits (
    limit_id SERIAL PRIMARY KEY,
    site_name TEXT UNIQUE NOT NULL,
    max_requests INTEGER NOT NULL DEFAULT 60,
    period_seconds INTEGER NOT NULL DEFAULT 300,
    concurrent_limit INTEGER DEFAULT 1,
    retry_after_seconds INTEGER DEFAULT 60,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT INTO rate_limits (site_name, max_requests, period_seconds) VALUES
('athome', 60, 300),
('suumo', 30, 300),
('ieichiba', 20, 300),
('zero_estate', 10, 300),
('jmty', 20, 300),
('homes', 30, 300),
('rakuten', 30, 300)
ON CONFLICT (site_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS rate_limit_tracker (
    tracker_id BIGSERIAL PRIMARY KEY,
    site_name TEXT NOT NULL,
    request_timestamp TIMESTAMP NOT NULL,
    response_time_ms INTEGER,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
    error_message TEXT,
    from_cache BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (site_name) REFERENCES rate_limits(site_name)
);

CREATE INDEX idx_tracker_site_time 
ON rate_limit_tracker(site_name, request_timestamp DESC);

CREATE INDEX idx_tracker_cache 
ON rate_limit_tracker(from_cache, request_timestamp DESC);

-- ============================================
-- 2. CACHING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS scraped_pages_cache (
    cache_id BIGSERIAL PRIMARY KEY,

    -- HTTP Response
    http_status INTEGER NOT NULL,
    http_headers JSONB,  -- PostgreSQL JSONB for better performance

    -- Content Storage
    raw_html TEXT,
    raw_html_size INTEGER,
    is_compressed BOOLEAN DEFAULT FALSE,
    parsed_data JSONB,  -- JSONB instead of TEXT

    -- Content Hash
    content_hash TEXT NOT NULL,

    -- Metadata
    scraper_version TEXT DEFAULT '1.0',
    user_agent TEXT,
    scraped_at TIMESTAMP NOT NULL,
    scraping_duration_ms INTEGER,
    parsing_success BOOLEAN DEFAULT TRUE,
    parsing_error TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cache_content_hash ON scraped_pages_cache(content_hash);
CREATE INDEX idx_cache_scraped_at ON scraped_pages_cache(scraped_at DESC);

CREATE TABLE IF NOT EXISTS cache_entries (
    entry_id BIGSERIAL PRIMARY KEY,

    -- URL Information
    original_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL UNIQUE,

    -- Source
    source_site TEXT NOT NULL,
    page_type TEXT NOT NULL CHECK(page_type IN ('list', 'detail', 'image')),

    -- Cache Status
    is_valid BOOLEAN DEFAULT TRUE,
    cache_hits INTEGER DEFAULT 0,

    -- Timestamps
    first_cached_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,

    -- Foreign Keys
    cache_id BIGINT,
    FOREIGN KEY (cache_id) REFERENCES scraped_pages_cache(cache_id) ON DELETE CASCADE,
    FOREIGN KEY (source_site) REFERENCES rate_limits(site_name)
);

CREATE INDEX idx_cache_url_hash ON cache_entries(url_hash);
CREATE INDEX idx_cache_normalized_url ON cache_entries(normalized_url);
CREATE INDEX idx_cache_expires ON cache_entries(expires_at, is_valid);
CREATE INDEX idx_cache_site_type ON cache_entries(source_site, page_type);

CREATE TABLE IF NOT EXISTS cache_stats (
    stat_id SERIAL PRIMARY KEY,
    stat_date DATE NOT NULL UNIQUE,

    -- Performance
    total_requests INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,
    cache_expired INTEGER DEFAULT 0,
    cache_invalidated INTEGER DEFAULT 0,

    -- Hit Rate (computed)
    hit_rate REAL GENERATED ALWAYS AS (
        CASE WHEN total_requests > 0 
        THEN CAST(cache_hits AS REAL) / total_requests 
        ELSE 0 END
    ) STORED,

    -- Savings
    bandwidth_saved_mb REAL DEFAULT 0,
    time_saved_seconds REAL DEFAULT 0,

    -- Storage
    total_cache_size_mb REAL DEFAULT 0,
    total_cache_entries INTEGER DEFAULT 0,
    entries_cleaned INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stats_date ON cache_stats(stat_date DESC);

-- ============================================
-- 3. PROPERTY TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS properties (
    property_id BIGSERIAL PRIMARY KEY,

    -- Source
    source_site TEXT NOT NULL,
    source_property_id TEXT NOT NULL,
    source_url TEXT,
    detail_page_cache_id BIGINT,

    -- Basic Info
    property_name TEXT,
    location_pref TEXT NOT NULL,
    location_city TEXT NOT NULL,
    location_detail TEXT,
    latitude REAL,
    longitude REAL,

    -- Size & Price
    area_sqm INTEGER,
    area_tsubo REAL,
    price_yen BIGINT,  -- BIGINT for large prices
    is_free BOOLEAN DEFAULT FALSE,

    -- Property Type
    property_type TEXT,
    building_age INTEGER,

    -- Access
    road_width_m REAL,
    access_status TEXT,
    nearest_station_km REAL,

    -- Location
    altitude_m INTEGER,
    slope_percent REAL,
    surrounding_env TEXT,
    population_density REAL,
    nearest_house_distance_m INTEGER,

    -- Utilities
    water_available BOOLEAN DEFAULT FALSE,
    electric_available BOOLEAN DEFAULT FALSE,
    telecom_coverage TEXT,

    -- Regulations
    agricultural_land BOOLEAN DEFAULT FALSE,
    buildable BOOLEAN DEFAULT TRUE,
    urban_planning_zone TEXT,

    -- Convenience
    nearest_conbini_km REAL,
    nearest_supermarket_km REAL,
    nearest_hospital_km REAL,

    -- Score
    campsite_score REAL DEFAULT 0,
    confidence_score REAL DEFAULT 0,

    -- Metadata
    listing_date DATE,
    scraped_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source_site, source_property_id),
    FOREIGN KEY (detail_page_cache_id) REFERENCES scraped_pages_cache(cache_id)
);

CREATE INDEX idx_properties_score ON properties(campsite_score DESC, is_active);
CREATE INDEX idx_properties_site ON properties(source_site, is_active);
CREATE INDEX idx_properties_cache ON properties(detail_page_cache_id);
CREATE INDEX idx_properties_location ON properties(location_pref, location_city);

CREATE TABLE IF NOT EXISTS property_images (
    image_id BIGSERIAL PRIMARY KEY,
    property_id BIGINT NOT NULL,
    image_url TEXT NOT NULL,
    image_type TEXT CHECK(image_type IN ('exterior', 'interior', 'map', 'other')),
    order_num INTEGER DEFAULT 0,
    image_cache_id BIGINT,
    scraped_at TIMESTAMP NOT NULL,
    FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE,
    FOREIGN KEY (image_cache_id) REFERENCES scraped_pages_cache(cache_id)
);

CREATE INDEX idx_images_property ON property_images(property_id, order_num);

-- ============================================
-- 4. AI SCORING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS ai_scores (
    score_id BIGSERIAL PRIMARY KEY,
    property_id BIGINT NOT NULL,

    area_score REAL DEFAULT 0 CHECK(area_score >= 0 AND area_score <= 25),
    neighbor_score REAL DEFAULT 0 CHECK(neighbor_score >= 0 AND neighbor_score <= 20),
    road_score REAL DEFAULT 0 CHECK(road_score >= 0 AND road_score <= 20),
    convenience_score REAL DEFAULT 0 CHECK(convenience_score >= 0 AND convenience_score <= 15),
    scenery_score REAL DEFAULT 0 CHECK(scenery_score >= 0 AND scenery_score <= 10),
    access_score REAL DEFAULT 0 CHECK(access_score >= 0 AND access_score <= 10),

    total_score REAL DEFAULT 0 CHECK(total_score >= 0 AND total_score <= 100),
    confidence REAL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),

    analysis_details JSONB,  -- JSONB for structured analysis

    calculated_at TIMESTAMP NOT NULL,
    model_version TEXT DEFAULT '1.0',

    FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE
);

CREATE INDEX idx_scores_total ON ai_scores(total_score DESC);
CREATE INDEX idx_scores_property ON ai_scores(property_id);

-- ============================================
-- 5. LOGGING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS scraping_logs (
    log_id BIGSERIAL PRIMARY KEY,
    batch_date DATE NOT NULL,
    source_site TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL CHECK(status IN ('running', 'success', 'failed', 'partial')),

    -- Results
    properties_found INTEGER DEFAULT 0,
    properties_new INTEGER DEFAULT 0,
    properties_updated INTEGER DEFAULT 0,

    -- Cache Statistics
    pages_cached INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,

    -- Errors
    errors_count INTEGER DEFAULT 0,
    error_messages TEXT,

    execution_time_sec REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_date ON scraping_logs(batch_date DESC, source_site);

CREATE TABLE IF NOT EXISTS daily_blogs (
    blog_id SERIAL PRIMARY KEY,
    blog_date DATE UNIQUE NOT NULL,
    markdown_path TEXT NOT NULL,
    properties_featured INTEGER DEFAULT 0,
    total_properties INTEGER DEFAULT 0,
    avg_score REAL,
    max_score REAL,
    hugo_built_at TIMESTAMP,
    git_commit_hash TEXT,
    published_url TEXT,
    generated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_blogs_date ON daily_blogs(blog_date DESC);

-- ============================================
-- 6. VIEWS
-- ============================================

CREATE OR REPLACE VIEW v_top_properties AS
SELECT 
    p.property_id,
    p.property_name,
    p.location_pref || ' ' || p.location_city AS location,
    p.area_sqm,
    p.price_yen,
    p.road_width_m,
    p.source_site,
    p.source_url,
    s.total_score,
    s.area_score,
    s.neighbor_score,
    s.road_score,
    p.scraped_at
FROM properties p
LEFT JOIN ai_scores s ON p.property_id = s.property_id
WHERE p.is_active = TRUE
ORDER BY s.total_score DESC;

CREATE OR REPLACE VIEW v_cache_performance AS
SELECT 
    ce.source_site,
    ce.page_type,
    COUNT(*) as total_entries,
    SUM(CASE WHEN ce.is_valid THEN 1 ELSE 0 END) as valid_entries,
    SUM(ce.cache_hits) as total_hits,
    AVG(spc.raw_html_size) as avg_size_bytes,
    SUM(CASE WHEN spc.is_compressed THEN 1 ELSE 0 END) as compressed_count
FROM cache_entries ce
JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
GROUP BY ce.source_site, ce.page_type;

-- ============================================
-- 7. FUNCTIONS (PostgreSQL specific)
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- ============================================
-- 8. TRIGGERS
-- ============================================

CREATE TRIGGER update_rate_limits_timestamp
    BEFORE UPDATE ON rate_limits
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_properties_timestamp
    BEFORE UPDATE ON properties
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cache_timestamp
    BEFORE UPDATE ON scraped_pages_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 9. INITIAL DATA SUMMARY
-- ============================================

SELECT 'Neon PostgreSQL schema initialized successfully!' AS status;

-- Show table counts
SELECT 
    schemaname,
    COUNT(*) as table_count
FROM pg_tables 
WHERE schemaname = 'public'
GROUP BY schemaname;
```

---

## Connection Configuration

### Update requirements.txt

```txt
# Remove (SQLite-only)
# sqlalchemy==2.0.23

# Add (PostgreSQL)
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
asyncpg==0.29.0  # Optional: for async support
```

### Environment Variables

**Create `.env` file:**

```bash
# Neon PostgreSQL Connection
DATABASE_URL=postgresql://seccamp_owner:AbCdEf123@ep-blue-sky-12345.ap-northeast-1.aws.neon.tech/seccamp?sslmode=require

# Alternative: Split format
NEON_USER=seccamp_owner
NEON_PASSWORD=AbCdEf123
NEON_HOST=ep-blue-sky-12345.ap-northeast-1.aws.neon.tech
NEON_DATABASE=seccamp
NEON_SSLMODE=require

# GitHub Token (existing)
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=username/seccamp
```

### Connection Manager

```python
# app/database/connection.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """
    Neon PostgreSQL connection manager
    """

    def __init__(self):
        # Get connection URL from environment
        self.database_url = os.getenv('DATABASE_URL')

        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Neon uses connection pooling, so we use NullPool
        self.engine = create_engine(
            self.database_url,
            poolclass=NullPool,
            echo=False,
            connect_args={
                "connect_timeout": 10,
                "options": "-c timezone=utc"
            }
        )

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info("✅ Connected to Neon PostgreSQL")

    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()

    def execute_raw(self, query: str, params: dict = None):
        """Execute raw SQL query"""
        with self.engine.connect() as conn:
            result = conn.execute(query, params or {})
            conn.commit()
            return result

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute("SELECT 1")
                logger.info("✅ Neon connection test successful")
                return True
        except Exception as e:
            logger.error(f"❌ Neon connection test failed: {e}")
            return False

# Singleton instance
db = DatabaseConnection()
```

---

## Code Migration

### Update CacheManager for PostgreSQL

```python
# app/scrapers/cache_manager.py (Updated)

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import hashlib
import zlib
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging
import json

class CacheManager:
    """
    Cache manager for Neon PostgreSQL
    """

    TTL_LIST_PAGE = 6 * 3600
    TTL_DETAIL_PAGE = 7 * 86400
    TTL_IMAGE = 30 * 86400

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.database_url = os.getenv('DATABASE_URL')

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(self.database_url)

    def get_cache(self, url: str, site_name: str, 
                  page_type: str = 'detail') -> Optional[Dict]:
        """Get cached page by URL"""
        from app.utils.url_normalizer import URLNormalizer

        normalized = URLNormalizer.normalize(url, site_name)
        url_hash = normalized['url_hash']

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
                    (url_hash,)
                )

                entry = cur.fetchone()

                if not entry:
                    self.logger.debug(f"Cache MISS: {url}")
                    self._record_miss(site_name)
                    return None

                # Update access stats
                cur.execute(
                    """
                    UPDATE cache_entries
                    SET cache_hits = cache_hits + 1,
                        last_accessed_at = CURRENT_TIMESTAMP
                    WHERE url_hash = %s
                    """,
                    (url_hash,)
                )
                conn.commit()

                # Decompress if needed
                raw_html = entry['raw_html']
                if entry['is_compressed']:
                    raw_html = zlib.decompress(raw_html.encode('latin1')).decode('utf-8')

                self.logger.info(f"✅ Cache HIT: {url[:80]}...")
                self._record_hit(site_name)

                return {
                    'cache_id': entry['cache_id'],
                    'url': normalized['normalized_url'],
                    'http_status': entry['http_status'],
                    'raw_html': raw_html,
                    'parsed_data': entry['parsed_data'],  # Already JSONB
                    'scraped_at': entry['scraped_at'],
                    'from_cache': True
                }

        except Exception as e:
            self.logger.error(f"Error getting cache: {e}")
            return None

        finally:
            conn.close()

    def set_cache(self, url: str, site_name: str, page_type: str,
                  http_status: int, raw_html: str,
                  parsed_data: Optional[dict] = None,
                  user_agent: Optional[str] = None,
                  scraping_duration_ms: Optional[int] = None,
                  ttl_override: Optional[int] = None) -> int:
        """Store page in cache"""
        from app.utils.url_normalizer import URLNormalizer

        normalized = URLNormalizer.normalize(url, site_name)

        # TTL
        ttl_map = {
            'list': self.TTL_LIST_PAGE,
            'detail': self.TTL_DETAIL_PAGE,
            'image': self.TTL_IMAGE
        }
        ttl_seconds = ttl_override or ttl_map.get(page_type, self.TTL_DETAIL_PAGE)

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Compress
        html_size = len(raw_html.encode('utf-8'))
        is_compressed = False
        if html_size > 10240:
            compressed = zlib.compress(raw_html.encode('utf-8'))
            if len(compressed) < html_size * 0.8:
                raw_html = compressed.decode('latin1')
                is_compressed = True

        content_hash = hashlib.sha256(raw_html.encode('utf-8')).hexdigest()

        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                # Check existing content
                cur.execute(
                    "SELECT cache_id FROM scraped_pages_cache WHERE content_hash = %s",
                    (content_hash,)
                )
                existing = cur.fetchone()

                if existing:
                    cache_id = existing[0]
                else:
                    # Insert cache content
                    cur.execute(
                        """
                        INSERT INTO scraped_pages_cache
                        (http_status, raw_html, raw_html_size, is_compressed,
                         parsed_data, content_hash, scraper_version, user_agent,
                         scraped_at, scraping_duration_ms, parsing_success)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING cache_id
                        """,
                        (
                            http_status,
                            raw_html,
                            html_size,
                            is_compressed,
                            json.dumps(parsed_data) if parsed_data else None,
                            content_hash,
                            '1.0',
                            user_agent,
                            now,
                            scraping_duration_ms,
                            True if parsed_data else False
                        )
                    )
                    cache_id = cur.fetchone()[0]

                # Insert/update entry
                cur.execute(
                    """
                    INSERT INTO cache_entries
                    (original_url, normalized_url, url_hash, source_site, page_type,
                     is_valid, cache_hits, first_cached_at, last_accessed_at,
                     expires_at, cache_id)
                    VALUES (%s, %s, %s, %s, %s, TRUE, 0, %s, %s, %s, %s)
                    ON CONFLICT (url_hash) DO UPDATE SET
                        cache_id = EXCLUDED.cache_id,
                        expires_at = EXCLUDED.expires_at,
                        last_accessed_at = EXCLUDED.last_accessed_at,
                        is_valid = TRUE
                    """,
                    (
                        normalized['original_url'],
                        normalized['normalized_url'],
                        normalized['url_hash'],
                        site_name,
                        page_type,
                        now,
                        now,
                        expires_at,
                        cache_id
                    )
                )

                conn.commit()
                self.logger.info(f"✅ Cached: {url[:80]}...")

                return cache_id

        except Exception as e:
            self.logger.error(f"Error setting cache: {e}")
            conn.rollback()
            raise

        finally:
            conn.close()

    def _record_hit(self, site_name: str):
        """Record cache hit"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                today = datetime.now().date()
                cur.execute(
                    """
                    INSERT INTO cache_stats (stat_date, total_requests, cache_hits)
                    VALUES (%s, 1, 1)
                    ON CONFLICT (stat_date) DO UPDATE SET
                        total_requests = cache_stats.total_requests + 1,
                        cache_hits = cache_stats.cache_hits + 1
                    """,
                    (today,)
                )
                conn.commit()
        finally:
            conn.close()

    def _record_miss(self, site_name: str):
        """Record cache miss"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                today = datetime.now().date()
                cur.execute(
                    """
                    INSERT INTO cache_stats (stat_date, total_requests, cache_misses)
                    VALUES (%s, 1, 1)
                    ON CONFLICT (stat_date) DO UPDATE SET
                        total_requests = cache_stats.total_requests + 1,
                        cache_misses = cache_stats.cache_misses + 1
                    """,
                    (today,)
                )
                conn.commit()
        finally:
            conn.close()
```

### Update RateLimiter for PostgreSQL

```python
# app/scrapers/rate_limiter.py (Updated)

import psycopg2
from datetime import datetime, timedelta
import time
import logging

class RateLimiter:
    """Rate limiter using Neon PostgreSQL"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.database_url = os.getenv('DATABASE_URL')

    def _get_connection(self):
        return psycopg2.connect(self.database_url)

    def can_make_request(self, site_name: str) -> dict:
        """Check if request can be made"""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                # Get rate limit config
                cur.execute(
                    """
                    SELECT max_requests, period_seconds
                    FROM rate_limits
                    WHERE site_name = %s
                    """,
                    (site_name,)
                )
                config = cur.fetchone()

                if not config:
                    return {'allowed': True, 'wait_seconds': 0}

                max_requests, period_seconds = config

                # Count recent requests
                window_start = datetime.utcnow() - timedelta(seconds=period_seconds)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM rate_limit_tracker
                    WHERE site_name = %s
                      AND request_timestamp >= %s
                      AND status = 'success'
                    """,
                    (site_name, window_start)
                )
                count = cur.fetchone()[0]

                if count >= max_requests:
                    # Get oldest request
                    cur.execute(
                        """
                        SELECT request_timestamp
                        FROM rate_limit_tracker
                        WHERE site_name = %s
                          AND request_timestamp >= %s
                          AND status = 'success'
                        ORDER BY request_timestamp ASC
                        LIMIT 1
                        """,
                        (site_name, window_start)
                    )
                    oldest = cur.fetchone()

                    if oldest:
                        expire_time = oldest[0] + timedelta(seconds=period_seconds)
                        wait_seconds = (expire_time - datetime.utcnow()).total_seconds()
                        return {'allowed': False, 'wait_seconds': max(0, wait_seconds)}

                return {'allowed': True, 'wait_seconds': 0}

        finally:
            conn.close()

    def wait_if_needed(self, site_name: str):
        """Wait if rate limit reached"""
        check = self.can_make_request(site_name)

        if not check['allowed']:
            wait_time = check['wait_seconds']
            self.logger.warning(f"⏱️  Rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time + 1)
            return True

        return False

    def record_request(self, site_name: str, status: str,
                      response_time_ms: int = None,
                      error_message: str = None):
        """Record request in database"""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rate_limit_tracker
                    (site_name, request_timestamp, response_time_ms, status, error_message)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (site_name, datetime.utcnow(), response_time_ms, status, error_message)
                )
                conn.commit()
        finally:
            conn.close()
```

---

## Data Migration

### Migration Script

```python
# scripts/migrate_sqlite_to_neon.py

import sqlite3
import psycopg2
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SQLiteToNeonMigrator:
    """
    Migrate data from SQLite to Neon PostgreSQL
    """

    def __init__(self, sqlite_path: str, neon_url: str):
        self.sqlite_path = sqlite_path
        self.neon_url = neon_url

    def migrate(self):
        """Run full migration"""
        logger.info("Starting migration from SQLite to Neon...")

        # Connect to both databases
        sqlite_conn = sqlite3.connect(self.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row

        neon_conn = psycopg2.connect(self.neon_url)

        try:
            # Migrate each table
            self.migrate_rate_limits(sqlite_conn, neon_conn)
            self.migrate_rate_limit_tracker(sqlite_conn, neon_conn)
            self.migrate_scraped_pages_cache(sqlite_conn, neon_conn)
            self.migrate_cache_entries(sqlite_conn, neon_conn)
            self.migrate_properties(sqlite_conn, neon_conn)
            self.migrate_ai_scores(sqlite_conn, neon_conn)
            self.migrate_property_images(sqlite_conn, neon_conn)
            self.migrate_scraping_logs(sqlite_conn, neon_conn)
            self.migrate_daily_blogs(sqlite_conn, neon_conn)
            self.migrate_cache_stats(sqlite_conn, neon_conn)

            logger.info("✅ Migration completed successfully!")

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            neon_conn.rollback()
            raise

        finally:
            sqlite_conn.close()
            neon_conn.close()

    def migrate_properties(self, sqlite_conn, neon_conn):
        """Migrate properties table"""
        logger.info("Migrating properties...")

        cur_sqlite = sqlite_conn.cursor()
        cur_neon = neon_conn.cursor()

        cur_sqlite.execute("SELECT COUNT(*) FROM properties")
        total = cur_sqlite.fetchone()[0]
        logger.info(f"Found {total} properties to migrate")

        cur_sqlite.execute("SELECT * FROM properties")

        for row in cur_sqlite:
            cur_neon.execute(
                """
                INSERT INTO properties (
                    property_id, source_site, source_property_id, source_url,
                    property_name, location_pref, location_city, area_sqm,
                    price_yen, is_free, road_width_m, scraped_at, last_seen_at,
                    is_active, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source_site, source_property_id) DO NOTHING
                """,
                (
                    row['property_id'],
                    row['source_site'],
                    row['source_property_id'],
                    row['source_url'],
                    row['property_name'],
                    row['location_pref'],
                    row['location_city'],
                    row['area_sqm'],
                    row['price_yen'],
                    bool(row['is_free']),
                    row['road_width_m'],
                    row['scraped_at'],
                    row['last_seen_at'],
                    bool(row['is_active']),
                    row.get('created_at', datetime.utcnow())
                )
            )

        neon_conn.commit()
        logger.info(f"✅ Migrated {total} properties")

    # ... Similar methods for other tables ...

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python migrate_sqlite_to_neon.py <sqlite_db_path>")
        sys.exit(1)

    sqlite_path = sys.argv[1]
    neon_url = os.getenv('DATABASE_URL')

    if not neon_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    migrator = SQLiteToNeonMigrator(sqlite_path, neon_url)
    migrator.migrate()
```

**Run migration:**

```bash
export DATABASE_URL='postgresql://...'
python scripts/migrate_sqlite_to_neon.py data/seccamp.db
```

---

## GitHub Actions Update

### Updated Workflow

```yaml
# .github/workflows/daily-batch.yml

name: SECCAMP Daily Batch (Neon)

on:
  schedule:
    - cron: '0 21 * * *'  # 06:00 JST
  workflow_dispatch:

env:
  DATABASE_URL: ${{ secrets.NEON_DATABASE_URL }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

jobs:
  run-batch:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Test Neon connection
        run: |
          python -c "
          from app.database.connection import db
          if db.test_connection():
              print('✅ Neon connection successful')
          else:
              print('❌ Neon connection failed')
              exit(1)
          "

      - name: Run scraping batch
        run: |
          python app/main.py --mode full

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./data/hugo_site/public
          publish_branch: gh-pages
```

### GitHub Secrets

Add in repository settings (Settings → Secrets → Actions):

```
NEON_DATABASE_URL = postgresql://seccamp_owner:password@ep-xxx.neon.tech/seccamp?sslmode=require
```

---

## Testing

### Test Connection

```python
# test_neon_connection.py

import os
from app.database.connection import db

def test_connection():
    print("Testing Neon PostgreSQL connection...")

    if db.test_connection():
        print("✅ Connection successful!")

        # Test query
        result = db.execute_raw("SELECT COUNT(*) FROM rate_limits")
        print(f"✅ Found {result.fetchone()[0]} rate limit configs")

        return True
    else:
        print("❌ Connection failed")
        return False

if __name__ == '__main__':
    test_connection()
```

### Test Cache

```python
# test_neon_cache.py

from app.scrapers.cache_manager import CacheManager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cache_mgr = CacheManager(logger)

# Test set
cache_mgr.set_cache(
    url='https://example.com/test',
    site_name='athome',
    page_type='detail',
    http_status=200,
    raw_html='<html>Test</html>'
)

# Test get
cached = cache_mgr.get_cache(
    'https://example.com/test',
    'athome',
    'detail'
)

if cached:
    print("✅ Cache test successful!")
else:
    print("❌ Cache test failed")
```

---

## Benefits Summary

### ✅ Advantages

1. **Persistent Storage** - No more Git commits of DB
2. **Auto-Scaling** - Neon handles scaling
3. **Connection Pooling** - Built-in pooling
4. **Backups** - Automatic backups
5. **Branching** - Test on branches before production
6. **Better Performance** - PostgreSQL > SQLite for concurrent access
7. **Free Tier** - 0.5 GB storage (enough for SECCAMP)

### ⚠️ Considerations

1. **Network Latency** - Slightly slower than local SQLite
2. **Free Tier Limits** - 0.5 GB storage (monitor usage)
3. **Connection String Security** - Store in GitHub Secrets

---

## Migration Checklist

- [ ] Create Neon account
- [ ] Create project in Tokyo region
- [ ] Save connection string
- [ ] Run PostgreSQL schema script
- [ ] Update requirements.txt
- [ ] Update CacheManager for PostgreSQL
- [ ] Update RateLimiter for PostgreSQL
- [ ] Create DatabaseConnection class
- [ ] Test connection
- [ ] Migrate existing data (if any)
- [ ] Update GitHub Actions workflow
- [ ] Add NEON_DATABASE_URL to secrets
- [ ] Test full workflow

---

## Cost Projection

**Neon Free Plan:**
- Storage: 0.5 GB (free)
- Compute: Always active (free)
- Data transfer: Unlimited (free)

**Expected SECCAMP Usage:**
- Storage: ~100-300 MB after 1 year ✅
- Compute: ~10 min/day ✅
- Connections: ~100/day ✅

**Verdict: Free tier is sufficient! 🎉**

---

**End of Migration Guide**
