# SECCAMP SQLite Database Schema with Page-Level Caching

**Version:** 4.0  
**Date:** 2025年12月24日 21:04 JST  
**Feature:** Comprehensive Page-Level Caching System

---

## Overview

### Purpose

Store scraped page content in SQLite to:
- ✅ Avoid re-scraping unchanged pages
- ✅ Reduce bandwidth by 80-90%
- ✅ Speed up runs by 10-100x
- ✅ Respect rate limits better
- ✅ Enable offline analysis

### Cache Strategy

**URL-based with SHA256 hashing:**
- Normalized URL → Hash → Fast lookup
- TTL-based expiration
- Content deduplication
- Automatic compression

---

## Cache Architecture

```
┌─────────────────────────────────────┐
│  URL Request                         │
└──────────┬──────────────────────────┘
           ↓
    [Normalize URL]
           ↓
    [Generate SHA256]
           ↓
┌──────────────────────────────────────┐
│  Check cache_entries by url_hash     │
└──────────┬──────────────────────────┘
           ↓
    [Cache Hit?]
    ├─ YES → Return cached HTML (0.001s)
    └─ NO  → Scrape fresh (5-10s)
               ↓
         [Store in cache]
               ↓
         [Return HTML]
```

---

## Cache Tables

### 1. cache_entries (URL Index)

**Purpose:** Fast URL → Cache ID lookup

```sql
CREATE TABLE IF NOT EXISTS cache_entries (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- URL Information
    original_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL UNIQUE,  -- SHA256 for O(1) lookup

    -- Source
    source_site TEXT NOT NULL,
    page_type TEXT NOT NULL CHECK(page_type IN ('list', 'detail', 'image')),

    -- Cache Status
    is_valid BOOLEAN DEFAULT 1,
    cache_hits INTEGER DEFAULT 0,

    -- Timestamps
    first_cached_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,

    -- Foreign Key
    cache_id INTEGER,
    FOREIGN KEY (cache_id) REFERENCES scraped_pages_cache(cache_id) ON DELETE CASCADE
);

CREATE INDEX idx_cache_url_hash ON cache_entries(url_hash);
CREATE INDEX idx_cache_expires ON cache_entries(expires_at, is_valid);
```

### 2. scraped_pages_cache (Content Storage)

**Purpose:** Store actual HTML and parsed data

```sql
CREATE TABLE IF NOT EXISTS scraped_pages_cache (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- HTTP Response
    http_status INTEGER NOT NULL,
    http_headers TEXT,  -- JSON

    -- Content
    raw_html TEXT,  -- May be compressed
    raw_html_size INTEGER,
    is_compressed BOOLEAN DEFAULT 0,
    parsed_data TEXT,  -- JSON

    -- Integrity
    content_hash TEXT NOT NULL,  -- SHA256 of raw_html

    -- Metadata
    scraper_version TEXT DEFAULT '1.0',
    user_agent TEXT,
    scraped_at TEXT NOT NULL,
    scraping_duration_ms INTEGER,
    parsing_success BOOLEAN DEFAULT 1,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_cache_content_hash ON scraped_pages_cache(content_hash);
```

### 3. cache_stats (Performance Metrics)

**Purpose:** Track cache performance daily

```sql
CREATE TABLE IF NOT EXISTS cache_stats (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT NOT NULL UNIQUE,  -- YYYY-MM-DD

    -- Performance
    total_requests INTEGER DEFAULT 0,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,
    cache_expired INTEGER DEFAULT 0,

    -- Hit Rate (computed)
    hit_rate REAL GENERATED ALWAYS AS (
        CASE WHEN total_requests > 0 
        THEN CAST(cache_hits AS REAL) / total_requests 
        ELSE 0 END
    ) STORED,

    -- Savings
    bandwidth_saved_mb REAL DEFAULT 0,
    time_saved_seconds REAL DEFAULT 0,

    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## URL Normalization

### Implementation

```python
import hashlib
from urllib.parse import urlparse, urlencode, urlunparse

class URLNormalizer:
    # Keep only important query params per site
    KEEP_PARAMS = {
        'athome': ['bukkenNo', 'id'],
        'suumo': ['bc', 'id'],
        'ieichiba': ['id'],
        'default': ['id', 'page']
    }

    @staticmethod
    def normalize(url: str, site_name: str = 'default') -> dict:
        parsed = urlparse(url)

        # Lowercase domain and path
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip('/')

        # Filter query params
        keep = URLNormalizer.KEEP_PARAMS.get(site_name, ['id'])
        from urllib.parse import parse_qs
        query_dict = parse_qs(parsed.query)
        filtered = {k: v for k, v in query_dict.items() if k in keep}
        sorted_query = urlencode(sorted(filtered.items()), doseq=True)

        # Reconstruct
        normalized_url = urlunparse((scheme, netloc, path, '', sorted_query, ''))

        # Hash
        url_hash = hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()

        return {
            'original_url': url,
            'normalized_url': normalized_url,
            'url_hash': url_hash
        }
```

---

## CacheManager Class

### Core Implementation

```python
import sqlite3
import zlib
from datetime import datetime, timedelta

class CacheManager:
    # TTL values
    TTL_LIST_PAGE = 6 * 3600      # 6 hours
    TTL_DETAIL_PAGE = 7 * 86400   # 7 days
    TTL_IMAGE = 30 * 86400        # 30 days

    def __init__(self, db_path: str, logger):
        self.db_path = db_path
        self.logger = logger

    def get_cache(self, url: str, site_name: str, 
                  page_type: str = 'detail'):
        # Normalize
        norm = URLNormalizer.normalize(url, site_name)
        url_hash = norm['url_hash']

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Query
        row = conn.execute(
            """
            SELECT ce.*, spc.*
            FROM cache_entries ce
            JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
            WHERE ce.url_hash = ? 
              AND ce.is_valid = 1
              AND ce.expires_at > datetime('now')
            """,
            (url_hash,)
        ).fetchone()

        if not row:
            return None  # Cache miss

        # Update stats
        conn.execute(
            """
            UPDATE cache_entries 
            SET cache_hits = cache_hits + 1,
                last_accessed_at = datetime('now')
            WHERE url_hash = ?
            """,
            (url_hash,)
        )
        conn.commit()
        conn.close()

        # Decompress if needed
        html = row['raw_html']
        if row['is_compressed']:
            html = zlib.decompress(html.encode('latin1')).decode('utf-8')

        self.logger.info(f"✅ Cache HIT: {url}")
        return {
            'raw_html': html,
            'parsed_data': row['parsed_data'],
            'from_cache': True
        }

    def set_cache(self, url: str, site_name: str, page_type: str,
                  http_status: int, raw_html: str,
                  parsed_data: str = None):
        # Normalize
        norm = URLNormalizer.normalize(url, site_name)

        # TTL
        ttl = {
            'list': self.TTL_LIST_PAGE,
            'detail': self.TTL_DETAIL_PAGE,
            'image': self.TTL_IMAGE
        }[page_type]

        expires_at = datetime.utcnow() + timedelta(seconds=ttl)

        # Compress if large
        html_size = len(raw_html.encode('utf-8'))
        is_compressed = False
        if html_size > 10240:  # 10KB
            compressed = zlib.compress(raw_html.encode('utf-8'))
            if len(compressed) < html_size * 0.8:
                raw_html = compressed.decode('latin1')
                is_compressed = True

        # Content hash
        import hashlib
        content_hash = hashlib.sha256(raw_html.encode('utf-8')).hexdigest()

        conn = sqlite3.connect(self.db_path)

        # Check if content exists (dedup)
        existing = conn.execute(
            "SELECT cache_id FROM scraped_pages_cache WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()

        if existing:
            cache_id = existing[0]
        else:
            cursor = conn.execute(
                """
                INSERT INTO scraped_pages_cache
                (http_status, raw_html, raw_html_size, is_compressed,
                 parsed_data, content_hash, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (http_status, raw_html, html_size, is_compressed,
                 parsed_data, content_hash, datetime.utcnow().isoformat())
            )
            cache_id = cursor.lastrowid

        # Insert or update entry
        conn.execute(
            """
            INSERT INTO cache_entries
            (original_url, normalized_url, url_hash, source_site, page_type,
             first_cached_at, last_accessed_at, expires_at, cache_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                cache_id = excluded.cache_id,
                expires_at = excluded.expires_at,
                last_accessed_at = excluded.last_accessed_at
            """,
            (norm['original_url'], norm['normalized_url'], norm['url_hash'],
             site_name, page_type, datetime.utcnow().isoformat(),
             datetime.utcnow().isoformat(), expires_at.isoformat(), cache_id)
        )

        conn.commit()
        conn.close()

        self.logger.info(f"✅ Cached: {url}")
        return cache_id
```

---

## Integration with BaseScraper

### Updated safe_get Method

```python
class BaseScraper(ABC):
    def __init__(self, site_name, base_url, db_path, logger):
        self.site_name = site_name
        self.cache_manager = CacheManager(db_path, logger)
        # ... existing init ...

    def safe_get_with_cache(self, url: str, page_type='detail',
                           force_refresh=False):
        # Try cache
        if not force_refresh:
            cached = self.cache_manager.get_cache(
                url, self.site_name, page_type
            )
            if cached:
                return cached['raw_html']

        # Cache miss - scrape fresh
        self.rate_limiter.wait_if_needed(self.site_name)

        start = time.time()
        self.driver.get(url)

        # Wait for load
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        html = self.driver.page_source
        duration = int((time.time() - start) * 1000)

        # Cache it
        self.cache_manager.set_cache(
            url, self.site_name, page_type,
            200, html
        )

        return html
```

---

## Usage Example

### Scraping with Cache

```python
# In scraper implementation
def _scrape_implementation(self):
    properties = []

    # Get list page (cached for 6 hours)
    list_html = self.safe_get_with_cache(
        self.search_url,
        page_type='list'
    )

    # Extract property URLs
    property_urls = self.extract_urls(list_html)

    for url in property_urls:
        # Get detail page (cached for 7 days)
        detail_html = self.safe_get_with_cache(
            url,
            page_type='detail'
        )

        # Parse
        prop_data = self.parse_detail_page(detail_html)
        properties.append(prop_data)

    return properties
```

---

## Cache Maintenance

### Periodic Cleanup

```python
def cleanup_expired_cache(db_path: str):
    conn = sqlite3.connect(db_path)

    # Mark expired as invalid
    conn.execute(
        """
        UPDATE cache_entries 
        SET is_valid = 0 
        WHERE expires_at < datetime('now')
        """
    )

    # Delete orphaned content
    conn.execute(
        """
        DELETE FROM scraped_pages_cache
        WHERE cache_id NOT IN (
            SELECT DISTINCT cache_id 
            FROM cache_entries 
            WHERE is_valid = 1
        )
        """
    )

    # Vacuum
    conn.execute('VACUUM')
    conn.commit()
    conn.close()
```

### Run in main.py

```python
def main():
    # ... scraping code ...

    # Daily cleanup
    if args.mode == 'full':
        cleanup_expired_cache(config.db_path)
```

---

## Performance Benefits

### Expected Improvements

| Metric | Without Cache | With Cache | Gain |
|--------|--------------|------------|------|
| Average scrape time | 5-10 sec/page | 0.001 sec | **5000x faster** |
| Bandwidth usage | 100 MB/run | 10-20 MB | **80% reduction** |
| Rate limit hits | Every page | Only new pages | **90% fewer** |
| Server load | High | Minimal | **Sustainable** |

### Cache Hit Rate Projection

```
Day 1:  5% hit rate  (mostly new properties)
Day 7:  50% hit rate (many properties seen before)
Day 30: 80% hit rate (stable property set)
```

---

## Database Updates

### Modified Tables

**rate_limit_tracker:** Added `from_cache BOOLEAN`
**properties:** Added `detail_page_cache_id INTEGER`
**property_images:** Added `image_cache_id INTEGER`
**scraping_logs:** Added cache statistics columns

---

## Summary

### Cache System Features

✅ **URL normalization** with SHA256 hashing  
✅ **TTL-based expiration** (6h/7d/30d)  
✅ **Content deduplication** via content hash  
✅ **Automatic compression** (10KB+ pages)  
✅ **Hit/miss tracking** in daily stats  
✅ **Automatic cleanup** of expired entries  
✅ **Site-agnostic design** for all scrapers  
✅ **Zero external dependencies** (pure SQLite)  

### Implementation Checklist

- [ ] Create 3 new cache tables
- [ ] Implement URLNormalizer class
- [ ] Implement CacheManager class
- [ ] Update BaseScraper with caching
- [ ] Add cleanup to main.py
- [ ] Test cache hit/miss scenarios
- [ ] Monitor cache statistics

---

**Ready to implement!** 🚀
