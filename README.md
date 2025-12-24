# SECCAMP - Private Campsite Search AI Agent

A batch automation system that searches and analyzes private campsite-suitable land from Japanese real estate websites.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Features

- **Web Scraping** - Scrapes 7 major Japanese real estate sites
- **Page-Level Caching** - SQLite-based cache with TTL (6h/7d/30d) and compression
- **Rate Limiting** - Real-time rate limiting with automatic waiting
- **AI Scoring** - 100-point campsite suitability evaluation (6 criteria)
- **Daily Blog** - Jinja2 template-based Markdown generation
- **Hugo Build** - Static site generation
- **Auto Deploy** - Git push to GitHub Pages

## Current Status

### Implemented ✅

- Docker multi-stage build with uv package manager
- SQLite database with complete schema (10 tables)
- Page-level caching system with compression
- Rate limiting per site with real-time tracking
- Base scraper class with Selenium integration
- Database ORM with SQLAlchemy models
- Development mode with hot-reload (`./run_dev.sh`)
- **AthomeScraper** - Scrape-only for debugging (saves HTML for inspection)

### Pending 🚧

- AthomeScraper parsing logic implementation
- Additional site scrapers (suumo, ieichiba, etc.)
- AI scoring engine implementation
- Blog generation with Jinja2 templates
- Hugo site building
- Git auto-push
- GitHub Actions workflow

## Quick Start

```bash
# Build
./build.sh

# Run in dev mode (hot-reload, no rebuild needed)
./run_dev.sh full

# Run specific mode
./run_dev.sh scrape

# Production run
./run_full.sh
```

## Project Structure

```
seccamp/
├── app/
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration from environment
│   ├── config/              # Site configuration
│   │   ├── site_config.py   # SiteConfig loader
│   │   └── sites.json       # Site URLs, selectors, rate limits
│   ├── database/            # Database layer
│   │   ├── models.py        # SQLAlchemy models
│   │   └── operations.py    # DatabaseManager
│   └── scrapers/            # Web scraping
│       ├── base_scraper.py  # Abstract base class
│       ├── athome_scraper.py # AtHome scraper (scrape-only for debugging)
│       ├── cache_manager.py # Page caching
│       ├── rate_limiter.py  # Rate limiting
│       └── url_normalizer.py # URL normalization
├── data/                    # Volume mapped
│   ├── seccamp.db           # SQLite database
│   ├── logs/                # Log files
│   ├── debug/               # Scraped HTML for debugging
│   └── hugo_site/           # Hugo site
├── refer/                   # Reference documentation
├── Dockerfile               # Multi-stage build with uv
├── docker-compose.yml       # Production
├── docker-compose.dev.yml   # Development (hot-reload)
└── run_*.sh                 # Convenience scripts
```

## Architecture

```
┌─────────────────────────────────────┐
│  URL Request                         │
└──────────┬──────────────────────────┘
           ↓
    [Check Cache]
    ├─ HIT → Return cached (0.001s)
    └─ MISS → [Check Rate Limit]
                  ├─ OK → Scrape
                  └─ WAIT → Scrape
                      ↓
                 [Store in Cache]
                      ↓
                 [Parse & Save to DB]
```

## Development

### Requirements

- Docker 24.0+
- Python 3.12+ (in container)
- Chrome + ChromeDriver (in container)
- Hugo Extended 0.120+ (in container)

### Environment Variables

```bash
# .env file
LOG_LEVEL=INFO
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=username/seccamp
GITHUB_USER=Your Name
GITHUB_EMAIL=your@email.com
HUGO_BASE_URL=https://username.github.io/seccamp/

# Scraping limits (for debugging)
MAX_DETAIL_PAGES=1  # Limit detail pages scraped per run
```

### Dev vs Production

| Mode | Compose File | Source Code | Rebuild |
|------|--------------|-------------|---------|
| Production | `docker-compose.yml` | Built into image | Required after changes |
| Dev | `docker-compose.dev.yml` | Mounted `./app` | Not needed |

### Debugging Scrapers

When `MAX_DETAIL_PAGES` is set, scraped HTML is saved for inspection:

```bash
# Run scraper
./run_dev.sh scrape

# Inspect output
ls -la data/debug/$(date +%Y-%m-%d)/
# Contains: athome_list.html, athome_detail_*.html
```

Use the saved HTML to understand the structure before implementing parsing logic.

## Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `rate_limits` | Rate limit config per site |
| `rate_limit_tracker` | Request history |
| `cache_entries` | URL index for cache lookup |
| `scraped_pages_cache` | Cached HTML content |
| `properties` | Master property data |
| `ai_scores` | AI analysis scores |
| `scraping_logs` | Scraping session logs |
| `daily_blogs` | Blog metadata |

### Cache TTL

- **List pages**: 6 hours
- **Detail pages**: 7 days
- **Images**: 30 days

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

---

# SECCAMP（プライベートキャンプ場探索AIエージェント）

日本の不動産サイトからプライベートキャンプ場に適した土地を自動検索・分析するバッチシステム。

**版:** 5.0 (AthomeScraper in Development)
**作成日:** 2025年12月24日
**最終更新:** 2025年12月24日

## 実装状況

### 実装済み ✅

- Dockerマルチステージビルド (uvパッケージマネージャー)
- SQLiteデータベース (完全スキーマ10テーブル)
- ページレベルキャッシュシステム (TTL 6h/7d/30d, 圧縮機能)
- レート制限システム (サイト別リアルタイム追跡)
- BaseScraperクラス (Selenium統合)
- DatabaseManager (SQLAlchemy ORM)
- 開発モード (ホットリロード)
- **AthomeScraper** - スクレイピング実装中（デバッグ用HTML保存）

### 未実装 🚧

- AthomeScraper パースロジック
- 他サイトスクレイパー (suumo, ieichiba等)
- AIスコアリングエンジン
- ブログ生成 (Jinja2)
- Hugoサイトビルド
- Git自動プッシュ
- GitHub Actions

---

**作成者:** SECCAMP開発チーム
**ライセンス:** Apache 2.0
