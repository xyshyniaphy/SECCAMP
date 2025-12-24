# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SECCAMP is a batch automation system that searches and analyzes private campsite-suitable land from Japanese real estate websites. The system runs daily at 06:00 JST via GitHub Actions, scrapes 7 major Japanese real estate sites, scores properties using AI analysis (100-point scale), and publishes results as a static Hugo website via GitHub Pages.

**Current Status:** Infrastructure implemented, AthomeScraper in active development (scrape-only for debugging). The data layer (database, caching, rate limiting) is complete.

## Architecture

### Technology Stack
- **Container:** Docker 24.0+ with multi-stage build (uv for venv)
- **Language:** Python 3.12+ (uv package manager)
- **Browser:** Chrome Headless for Selenium web scraping
- **Database:** SQLite 3.40+ with real-time rate limiting
- **Static Site Generator:** Hugo Extended 0.120+
- **Template Engine:** Jinja2 3.1+
- **ORM:** SQLAlchemy 2.0+

### System Flow
```
1. Check Cache → 2. Check Rate Limit → 3. Scrape → 4. Cache Results → 5. Parse & Save to DB
```

### Project Structure
```
seccamp/
├── app/
│   ├── main.py              # Entry point with CLI args (--mode scrape/full)
│   ├── config.py            # Configuration loading from environment
│   ├── config/              # Site configuration
│   │   ├── site_config.py   # SiteConfig loader
│   │   └── sites.json       # Site URLs, selectors, rate limits
│   ├── scrapers/            # Web scraping modules
│   │   ├── base_scraper.py  # Abstract base class with cache/rate limit
│   │   ├── athome_scraper.py # AtHome.co.jp scraper (scrape-only for debugging)
│   │   ├── cache_manager.py # Page-level caching with TTL
│   │   ├── rate_limiter.py  # SQLite-based rate limiting
│   │   └── url_normalizer.py # URL normalization for cache keys
│   ├── database/            # SQLAlchemy models + DatabaseManager
│   │   ├── models.py        # All 10 ORM models
│   │   └── operations.py    # DatabaseManager with CRUD operations
│   ├── analyzers/           # AI scoring engine (6 criteria, 100 points max) [PENDING]
│   ├── blog_generator/      # Jinja2 templates + daily post generation [PENDING]
│   └── utils/               # Logger, GitPusher [PENDING]
├── data/                    # Volume-mapped directory
│   ├── seccamp.db           # SQLite database (auto-initialized)
│   ├── logs/                # Daily log files
│   ├── debug/               # Scraped HTML for debugging (by date)
│   └── hugo_site/           # Hugo site [PENDING]
├── refer/                   # Reference documentation and configs
└── .github/workflows/
    └── daily-batch.yml      # Scheduled at 06:00 JST [PENDING]
```

## Development Commands

```bash
# Build Docker image
docker compose build
./build.sh

# Production run (uses built image)
docker compose run --rm seccamp --mode scrape
docker compose run --rm seccamp --mode full
./run_scrape.sh
./run_full.sh

# Development run (mounts app/ for hot-reload, no rebuild needed)
./run_dev.sh scrape
./run_dev.sh full
docker compose -f docker-compose.dev.yml run --rm seccamp --mode full

# Debug shell inside container
docker compose run --rm --entrypoint /bin/bash seccamp

# View logs
docker compose logs -f

# View daily log file
tail -f data/logs/seccamp-$(date +%Y-%m-%d).log

# Inspect scraped HTML (for debugging)
ls -la data/debug/$(date +%Y-%m-%d)/
# Contains: athome_list.html, athome_detail_*.html

# Check database
sqlite3 data/seccamp.db "SELECT * FROM scraping_logs ORDER BY started_at DESC LIMIT 10"
```

**Dev vs Production:**
- **Production** (`docker-compose.yml`): Uses built image, requires rebuild after code changes
- **Dev** (`docker-compose.dev.yml`): Mounts `app/` directory, changes apply instantly without rebuild

## Key Components

### DatabaseManager (`app/database/operations.py`)

Central database operations class. Usage:

```python
from database import DatabaseManager

db = DatabaseManager(config.db_path)

# Property operations
property_id = db.upsert_property(session, {
    "source_site": "athome",
    "source_property_id": "12345",
    "location_pref": "長野県",
    "location_city": "茅野市",
    "area_sqm": 5000,
    # ... other fields
})

# AI scoring
db.save_ai_score(session, property_id, {
    "area_score": 25.0,
    "neighbor_score": 20.0,
    # ... other scores
    "total_score": 85.0
})

# Top properties
top_props = db.get_top_properties(session, limit=50)

# Cache cleanup
result = db.cleanup_expired_cache()
```

### BaseScraper (`app/scrapers/base_scraper.py`)

Abstract base class for all scrapers. Subclasses implement `_scrape_implementation()`:

```python
from scrapers import BaseScraper

class AtHomeScraper(BaseScraper):
    def _scrape_implementation(self) -> List[Dict]:
        # Use safe_get_with_cache for automatic caching
        html = self.safe_get_with_cache(
            "https://example.com/list",
            page_type="list"
        )

        # Parse and return properties
        return [...]
```

The base class provides:
- `safe_get_with_cache(url, page_type)` - Get HTML with caching
- `rate_limiter` - Automatic rate limiting
- `cache_manager` - Page caching with TTL

### Database Concurrency

**Important:** The system uses SQLite with WAL (Write-Ahead Logging) mode for concurrent access:

- DatabaseManager enables WAL mode on initialization (before any sessions)
- CacheManager and RateLimiter use raw sqlite3 with 30s timeout
- SQLAlchemy sessions (via DatabaseManager) coexist with raw connections

**If you get "database is locked" errors:**
1. Ensure only one DatabaseManager instance exists per process
2. Close sessions when done (`session.close()`)
3. WAL mode should be enabled automatically - check logs for "WAL mode enabled"

### AthomeScraper (`app/scrapers/athome_scraper.py`)

**Current Status:** Scrape-only for debugging (no parsing logic yet)

Scrapes AtHome.co.jp and saves raw HTML for inspection:
- Scrapes list page for property URLs
- Scrapes detail pages (limited by `MAX_DETAIL_PAGES`)
- Saves HTML to `data/debug/{YYYY-MM-DD}/`
- Returns dict with raw HTML (not parsed data)

Usage:
```python
from scrapers import AthomeScraper

scraper = AthomeScraper(
    db_path=config.db_path,
    max_detail_pages=config.max_detail_pages,
)
result = scraper.scrape()
# result = {
#     "prefecture": "nagano",
#     "list_url": "...",
#     "list_html": "...",
#     "property_urls": ["url1", "url2", ...],
#     "detail_pages": {"url1": "<html>...", ...}
# }
```

### SiteConfig (`app/config/site_config.py`)

Loads site configuration from `app/config/sites.json`:

```python
from config.site_config import SiteConfig

site_config = SiteConfig()
athome = site_config.get_site("athome")
entry_urls = site_config.get_entry_urls("athome")
selectors = site_config.get_selectors("athome", "detail_page")
rate_limit = site_config.get_rate_limit("athome")
```

Configuration in `sites.json`:
- `site_name`, `display_name`, `base_url`
- `enabled` - enable/disable scraper
- `rate_limit` - max_requests, period_seconds
- `entry_urls` - per-prefecture list page URLs
- `selectors` - CSS selectors for list/detail pages
- `pagination` - pagination settings

### CacheManager (`app/scrapers/cache_manager.py`)

Page-level caching with TTL:
- List pages: 6 hours
- Detail pages: 7 days
- Images: 30 days

Features:
- SHA256 URL hashing for O(1) lookup
- Content deduplication
- Automatic compression (>10KB)
- Daily statistics tracking

### RateLimiter (`app/scrapers/rate_limiter.py`)

Per-site rate limiting with automatic waiting:

| Site | Max Requests | Period |
|------|--------------|--------|
| athome | 60 | 5 min |
| suumo | 30 | 5 min |
| ieichiba | 20 | 5 min |
| zero_estate | 10 | 5 min |
| jmty | 20 | 5 min |

## Database Schema

Key tables:
- `rate_limits` - Rate limit config per site
- `rate_limit_tracker` - Request history for rate limit calculation
- `cache_entries` - URL index for cache (with SHA256 hash)
- `scraped_pages_cache` - Cached HTML content (compressed)
- `properties` - Master property data with `campsite_score`
- `ai_scores` - Detailed breakdown of 6 scoring criteria
- `scraping_logs` - Scraping session logs with cache stats
- `daily_blogs` - Blog post metadata

## Environment Variables

Required in `.env`:
```
LOG_LEVEL=INFO
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=username/seccamp
GITHUB_USER=Your Name
GITHUB_EMAIL=your@email.com
HUGO_BASE_URL=https://username.github.io/seccamp/

# Scraping limits (for debugging)
MAX_DETAIL_PAGES=1  # Limit detail pages scraped per run
```

## Important Implementation Notes

1. **Database Auto-Initialization**: The database is automatically initialized from `app/init_database_complete.sql` on first run. The check looks for the `rate_limits` table existence.

2. **Chrome/ChromeDriver**: Uses Chrome for Testing API to download matching ChromeDriver version.

3. **Rate Limit Respect**: All scrapers MUST use `safe_get_with_cache()` which handles both caching and rate limiting automatically.

4. **Idempotency**: Properties use `UNIQUE(source_site, source_property_id)` to avoid duplicates.

5. **Cache TTL**: Choose appropriate page_type when calling `safe_get_with_cache()`:
   - `"list"` for listing pages (6h TTL)
   - `"detail"` for property pages (7d TTL)
   - `"image"` for images (30d TTL)

6. **Dev Mode**: Use `docker-compose.dev.yml` for development - source files are mounted so changes apply instantly without rebuilding.

7. **Git Operations:** Only commit/push `public/` and `content/posts/` directories.

8. **Debug Output**: When `MAX_DETAIL_PAGES` is set, scraped HTML is saved to `data/debug/{YYYY-MM-DD}/` for inspection. Use this to understand HTML structure before implementing parsing.

## Japanese Context

This project targets Japanese real estate sites. The specification is written in Japanese. Key search terms and site structures are Japan-specific.

Target sites:
- AtHome (athome.co.jp) - 18 prefectures configured
- SUUMO (suumo.jp)
- Ieichiba (ieichiba.com)
- Zero Estate (zero.estate)
- JMty (jmty.jp)

### AtHome.co.jp Details

**URL Patterns:**
- List: `https://www.athome.co.jp/kodate/chuko/{pref}/list/?pref={code}&basic=...`
- Detail: `https://www.athome.co.jp/kodate/{bukken_no}/?DOWN=1&...`

**Configured Prefectures:**
hokkaido, aomori, iwate, miyagi, akita, yamagata, fukushima, ibaraki, tochigi, gunma, saitama, chiba, tokyo, kanagawa, niigata, yamanashi, nagano, shizuoka

**Search Criteria (encoded in URL):**
- 土地面積1000㎡以上 (1000m²+ land area)
- 価格3000万円以下 (≤30M JPY)
- 平屋・2階建て (1-2 story buildings)
