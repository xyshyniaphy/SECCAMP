# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SECCAMP is a batch automation system that searches and analyzes private campsite-suitable land from Japanese real estate websites. The system runs daily at 06:00 JST via GitHub Actions, scrapes 7 major Japanese real estate sites, scores properties using AI analysis (100-point scale), and publishes results as a static Hugo website via GitHub Pages.

**Current Status:** Specification only. No implementation exists yet. The README.md (in Japanese) contains the complete technical specification for building this system from scratch.

## Architecture

### Technology Stack
- **Container:** Docker 24.0+ with multi-stage build (uv for venv)
- **Language:** Python 3.12+ (uv package manager)
- **Browser:** Chrome Headless for Selenium web scraping
- **Database:** SQLite 3.40+ with real-time rate limiting
- **Static Site Generator:** Hugo Extended 0.120+
- **Template Engine:** Jinja2 3.1+

### System Flow
```
1. Scrape (Rate Limited) → 2. Analyze & Score → 3. Generate Markdown → 4. Hugo Build → 5. Git Push
```

### Planned Directory Structure
```
seccamp/
├── app/
│   ├── main.py              # Entry point with CLI args (--mode scrape/full)
│   ├── config.py            # Configuration loading
│   ├── scrapers/            # Web scraping modules
│   │   ├── base_scraper.py  # Abstract base class
│   │   ├── rate_limiter.py  # SQLite-based rate limiting
│   │   └── *_scraper.py     # Site-specific scrapers
│   ├── database/            # SQLAlchemy models + operations
│   ├── analyzers/           # AI scoring engine (6 criteria, 100 points max)
│   ├── blog_generator/      # Jinja2 templates + daily post generation
│   └── utils/               # Logger, GitPusher
├── data/                    # Volume-mapped directory
│   ├── seccamp.db
│   ├── logs/
│   └── hugo_site/
│       ├── content/posts/   # Daily markdown files (YYYY-MM-DD.md)
│       └── public/          # Built Hugo site
└── .github/workflows/
    └── daily-batch.yml      # Scheduled at 06:00 JST
```

## Development Commands

```bash
# Build Docker image
docker-compose build

# Run full batch (scrape → analyze → generate → build → push)
docker-compose up

# Run specific mode only
docker-compose run --rm seccamp --mode scrape
docker-compose run --rm seccamp --mode full

# Debug shell inside container
docker-compose run --rm --entrypoint /bin/bash seccamp

# View logs
docker-compose logs -f

# View daily log file
tail -f data/logs/seccamp-$(date +%Y-%m-%d).log

# Check database
sqlite3 data/seccamp.db "SELECT * FROM scraping_logs ORDER BY started_at DESC LIMIT 10"
```

## Key Components

### Rate Limiting System
SQLite-based real-time rate limiting. Each site has configurable `max_requests` per `period_seconds`. The system tracks all requests in `rate_limit_tracker` table and automatically waits when limits are reached.

**Target sites:** athome (60/5min), suumo (30/5min), ieichiba (20/5min), zero.estate (10/5min), jmty (20/5min)

### AI Scoring (100 points total)
| Criteria | Points | Key Thresholds |
|----------|--------|----------------|
| Area | 0-25 | Ideal: 5000m²+, Min: 1000m² |
| Neighbor consideration | 0-20 | ★★★ 500m+ recommended for generator use |
| Road suitability | 0-20 | ★★★ 4.5m+ for camping car access |
| Convenience | 0-15 | Nearby convenience store |
| Scenery | 0-10 | Subjective assessment |
| Access | 0-10 | Nearby station |

### Search Criteria Priority
- **Area:** 1,000㎡ minimum (★★★)
- **Road width:** 4.5m+ for camping cars (★★★)
- **Population density:** 50 people/km² or less (★★★)
- **Nearest house:** 500m+ recommended for generator use (★★★)
- **Region:** Kanto and Chubu prioritized (★★)
- **Price:** 30 million yen or less (★★)

## Database Schema

Key tables:
- `rate_limits` - Rate limit config per site
- `rate_limit_tracker` - Request history for rate limit calculation
- `properties` - Master property data with `campsite_score`
- `ai_scores` - Detailed breakdown of 6 scoring criteria
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
```

## Important Implementation Notes

1. **Chrome/ChromeDriver Version Matching:** The Dockerfile installs Chrome and then downloads the matching ChromeDriver version dynamically. If scraping fails, rebuild with `--no-cache`.

2. **Rate Limit Respect:** The system MUST respect rate limits. Use `rate_limiter.wait_if_needed(site_name)` before every request.

3. **Idempotency:** Properties use `UNIQUE(source_site, source_property_id)` to avoid duplicates.

4. **Markdown Front Matter:** Daily posts require Hugo front matter with title, date (T06:00:00+09:00 format), and tags.

5. **Git Operations:** Only commit/push `public/` and `content/posts/` directories. Use the non-container user for proper permissions.

## Japanese Context

This project targets Japanese real estate sites. The specification is written in Japanese. Key search terms and site structures are Japan-specific.
