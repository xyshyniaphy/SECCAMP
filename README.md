# SECCAMP（プライベートキャンプ場探索AIエージェント）完全仕様書

**版:** 3.0 (Complete)  
**作成日:** 2025年12月24日  
**最終更新:** 2025年12月24日 19:35 JST  
**文書種別:** 実装用詳細仕様書  
**対象:** 開発者・運用担当者

---

## エグゼクティブサマリー

本文書は、プライベートキャンプ場に適した土地を自動検索・分析し、日次ブログとして公開するバッチシステム「SECCAMP」の完全な技術仕様書です。

### システム特性

- **実行モデル:** 日次単一実行（Run Once Daily）
- **コンテナ化:** Docker完全隔離環境
- **データベース:** SQLite（レート制限リアルタイム計算機能付き）
- **出力形式:** Markdown日次ブログ（YYYY-MM-DD.md）
- **静的サイト:** Hugo生成
- **ホスティング:** GitHub Pages自動デプロイ
- **自動化:** GitHub Actions（毎朝06:00 JST実行）

### 主要機能

1. **Web Scraping** - 日本主要不動産サイト7社から自動収集
2. **SQLite Rate Limiting** - リアルタイムレート制限計算・自動待機
3. **AI Scoring** - 100点満点キャンプ適性評価（6項目分析）
4. **Daily Blog** - Jinja2テンプレートによる日次Markdown生成
5. **Hugo Build** - 全履歴記事を静的HTML化
6. **Git Auto-Push** - GitHub自動プッシュ・Pages公開

---

## 目次

1. [システム概要](#1-システム概要)
2. [アーキテクチャ設計](#2-アーキテクチャ設計)
3. [技術スタック](#3-技術スタック)
4. [ディレクトリ構造](#4-ディレクトリ構造)
5. [Docker環境](#5-docker環境)
6. [データベース設計](#6-データベース設計)
7. [レート制限システム](#7-レート制限システム)
8. [スクレイピング実装](#8-スクレイピング実装)
9. [AI分析エンジン](#9-ai分析エンジン)
10. [ブログ生成システム](#10-ブログ生成システム)
11. [Hugo静的サイト](#11-hugo静的サイト)
12. [Git自動公開](#12-git自動公開)
13. [エラーハンドリング](#13-エラーハンドリング)
14. [GitHub Actions](#14-github-actions)
15. [運用手順](#15-運用手順)
16. [付録](#16-付録)

---

## 1. システム概要

### 1.1 プロジェクト目的

日本全国の不動産サイトからプライベートキャンプ場に適した土地を自動収集し、AI分析によってスコアリングし、結果を日次ブログとして自動公開する完全自動化バッチシステム。

### 1.2 ターゲットユーザー

- プライベートキャンプ場購入検討者
- キャンピングカーユーザー（定住地探し）
- オフグリッド生活希望者
- 小規模キャンプ場経営者

### 1.3 重要検索条件

| 項目 | 条件 | 優先度 | 理由 |
|------|------|--------|------|
| 広さ | 1,000㎡以上 | ★★★ | キャンプ場として十分な広さ |
| 道路幅員 | 4.5m以上 | ★★★ | キャンピングカー通行可 |
| 周辺人口密度 | 50人/km²以下 | ★★★ | 静寂性確保 |
| 最近隣住宅 | 500m以上推奨 | ★★★ | 発電機使用時の配慮 |
| 地域 | 関東・中部優先 | ★★ | アクセス利便性 |
| 価格 | 3,000万円以下 | ★★ | 現実的な予算 |

---

## 2. アーキテクチャ設計

### 2.1 システム全体図

```
┌──────────────────────────────────────────┐
│        Host Machine (Linux/Mac/Win)       │
│                                           │
│  ┌────────────────────────────────────┐  │
│  │   Docker Container (Daily Run)     │  │
│  │                                    │  │
│  │  ┌──────────────────────────────┐ │  │
│  │  │  Python 3.12 + Chrome + Hugo │ │  │
│  │  │                              │ │  │
│  │  │  [Batch Agent Process]       │ │  │
│  │  │  1. Scrape (Rate Limited)    │ │  │
│  │  │  2. Analyze & Score          │ │  │
│  │  │  3. Generate Markdown        │ │  │
│  │  │  4. Hugo Build               │ │  │
│  │  │  5. Git Push                 │ │  │
│  │  └──────────────────────────────┘ │  │
│  └────────────────────────────────────┘  │
│                                           │
│  📁 ./data/ (Volume Mapped)               │
│     ├── seccamp.db                        │
│     ├── logs/                             │
│     └── hugo_site/                        │
│         ├── content/posts/*.md            │
│         └── public/ (Built Site)          │
└──────────────────────────────────────────┘
                    ↓
        ┌───────────────────────┐
        │  GitHub Repository     │
        │  (gh-pages branch)     │
        └───────────┬───────────┘
                    ↓
        ┌───────────────────────┐
        │   GitHub Pages        │
        │   Public Website      │
        └───────────────────────┘
```

### 2.2 実行フローチャート

```
START
  ↓
[Initialize]
├─ Load .env
├─ Setup logger
└─ Connect SQLite
  ↓
[Scraping Loop]
For each site:
  ├─ Load rate config
  ├─ Check current count
  ├─ Wait if needed
  ├─ Scrape pages
  ├─ Record request
  └─ Save to DB
  ↓
[AI Analysis]
For each property:
  ├─ Calculate 6 scores
  ├─ Sum to total (0-100)
  └─ Save to ai_scores
  ↓
[Blog Generation]
├─ Get TOP 50 props
├─ Calculate stats
├─ Render Jinja2
└─ Save YYYY-MM-DD.md
  ↓
[Hugo Build]
├─ Run: hugo --minify
├─ Compile all posts
└─ Generate public/
  ↓
[Git Push]
├─ Add changes
├─ Commit
└─ Push to remote
  ↓
[Cleanup & Exit]
END
```

---

## 3. 技術スタック

### 3.1 コア技術一覧

| カテゴリ | 技術 | バージョン | 用途 |
|---------|------|-----------|------|
| Container | Docker | 24.0+ | 環境隔離 |
| Base OS | Debian 12 (Bookworm) | - | Pythonベースイメージ |
| Language | Python | 3.12+ | メインロジック |
| Browser | Chrome Headless | Latest | スクレイピング |
| Database | SQLite | 3.40+ | データ永続化 |
| Static Gen | Hugo Extended | 0.120+ | 静的サイト |
| Template | Jinja2 | 3.1+ | Markdown生成 |
| VCS | Git | 2.40+ | バージョン管理 |

### 3.2 Python依存関係

```txt
# Core Web Scraping
selenium==4.16.0
beautifulsoup4==4.12.2
lxml==4.9.3
requests==2.31.0

# Database
sqlalchemy==2.0.23

# Template & Markdown
jinja2==3.1.2
markdown==3.5.1
pyyaml==6.0.1

# Utilities
python-dotenv==1.0.0
tenacity==8.2.3

# Optional
pandas==2.1.4
```

---

## 4. ディレクトリ構造

```
seccamp/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
│
├── .github/
│   └── workflows/
│       └── daily-batch.yml
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py
│   │   ├── rate_limiter.py
│   │   ├── athome_scraper.py
│   │   ├── suumo_scraper.py
│   │   └── ieichiba_scraper.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── operations.py
│   ├── analyzers/
│   │   ├── __init__.py
│   │   └── scorer.py
│   ├── blog_generator/
│   │   ├── __init__.py
│   │   ├── daily_post.py
│   │   ├── hugo_builder.py
│   │   └── templates/
│   │       └── daily_post.j2
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── git_pusher.py
│
└── data/  (🔵 VOLUME MAPPED)
    ├── seccamp.db
    ├── logs/
    │   └── seccamp-YYYY-MM-DD.log
    └── hugo_site/
        ├── config.toml
        ├── content/
        │   └── posts/
        │       ├── 2025-12-24.md
        │       └── ...
        ├── themes/
        │   └── seccamp-theme/
        ├── static/
        └── public/
```

---

## 5. Docker環境

### 5.1 Dockerfile

```dockerfile
FROM python:3.12-slim

ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates git unzip \
    fonts-liberation libasound2 libatk-bridge2.0-0 \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1) \
    && CHROMEDRIVER_VERSION=$(curl -sS "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip && mv chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver && rm chromedriver_linux64.zip

# Install Hugo
ARG HUGO_VERSION=0.120.4
RUN wget -q "https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz" \
    && tar -xzf hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz \
    && mv hugo /usr/local/bin/ && chmod +x /usr/local/bin/hugo \
    && rm hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

RUN mkdir -p /data/logs /data/hugo_site/content/posts

VOLUME ["/data"]

RUN useradd -m -u 1000 seccamp && chown -R seccamp:seccamp /app /data
USER seccamp

ENTRYPOINT ["python", "main.py"]
CMD ["--mode", "full"]
```

### 5.2 docker-compose.yml

```yaml
version: '3.8'

services:
  seccamp:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: seccamp-batch
    volumes:
      - ./data:/data
    environment:
      - PYTHONUNBUFFERED=1
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - GITHUB_REPO=${GITHUB_REPO}
    env_file:
      - .env
    restart: "no"
    networks:
      - seccamp-network

networks:
  seccamp-network:
    driver: bridge
```

### 5.3 実行コマンド

```bash
# Build
docker-compose build

# Run full batch
docker-compose up

# Run specific mode
docker-compose run --rm seccamp --mode scrape
docker-compose run --rm seccamp --mode full

# Debug shell
docker-compose run --rm --entrypoint /bin/bash seccamp

# View logs
docker-compose logs -f
```

---

## 6. データベース設計

### 6.1 主要テーブル

#### rate_limits (レート制限設定)

```sql
CREATE TABLE rate_limits (
    limit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT UNIQUE NOT NULL,
    max_requests INTEGER NOT NULL DEFAULT 60,
    period_seconds INTEGER NOT NULL DEFAULT 300,
    created_at TEXT DEFAULT (datetime('now'))
);

INSERT INTO rate_limits (site_name, max_requests, period_seconds) VALUES
('athome', 60, 300),
('suumo', 30, 300),
('ieichiba', 20, 300);
```

#### rate_limit_tracker (リクエスト履歴)

```sql
CREATE TABLE rate_limit_tracker (
    tracker_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT NOT NULL,
    request_timestamp TEXT NOT NULL,
    response_time_ms INTEGER,
    status TEXT CHECK(status IN ('success', 'failed', 'timeout')),
    FOREIGN KEY (site_name) REFERENCES rate_limits(site_name)
);

CREATE INDEX idx_tracker_site_time 
ON rate_limit_tracker(site_name, request_timestamp DESC);
```

#### properties (物件マスター)

```sql
CREATE TABLE properties (
    property_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_site TEXT NOT NULL,
    source_property_id TEXT NOT NULL,
    property_name TEXT,
    location_pref TEXT NOT NULL,
    location_city TEXT NOT NULL,
    area_sqm INTEGER,
    price_yen INTEGER,
    is_free BOOLEAN DEFAULT 0,
    road_width_m REAL,
    population_density REAL,
    nearest_house_distance_m INTEGER,
    campsite_score REAL DEFAULT 0,
    scraped_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(source_site, source_property_id)
);

CREATE INDEX idx_score ON properties(campsite_score DESC);
```

#### ai_scores (AIスコア)

```sql
CREATE TABLE ai_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    area_score REAL DEFAULT 0 CHECK(area_score >= 0 AND area_score <= 25),
    neighbor_score REAL DEFAULT 0 CHECK(neighbor_score >= 0 AND neighbor_score <= 20),
    road_score REAL DEFAULT 0 CHECK(road_score >= 0 AND road_score <= 20),
    convenience_score REAL DEFAULT 0 CHECK(convenience_score >= 0 AND convenience_score <= 15),
    scenery_score REAL DEFAULT 0 CHECK(scenery_score >= 0 AND scenery_score <= 10),
    access_score REAL DEFAULT 0 CHECK(access_score >= 0 AND access_score <= 10),
    total_score REAL DEFAULT 0 CHECK(total_score >= 0 AND total_score <= 100),
    confidence REAL DEFAULT 0,
    calculated_at TEXT NOT NULL,
    FOREIGN KEY (property_id) REFERENCES properties(property_id)
);
```

#### daily_blogs (ブログメタデータ)

```sql
CREATE TABLE daily_blogs (
    blog_id INTEGER PRIMARY KEY AUTOINCREMENT,
    blog_date TEXT UNIQUE NOT NULL,
    markdown_path TEXT NOT NULL,
    properties_featured INTEGER DEFAULT 0,
    hugo_built_at TEXT,
    git_commit_hash TEXT,
    generated_at TEXT NOT NULL
);
```

---

## 7. レート制限システム

### 7.1 リアルタイム計算ロジック

```python
def can_make_request(self, site_name: str) -> Dict:
    # Get config
    max_requests = 60
    period_seconds = 300  # 5 minutes

    # Current window
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=period_seconds)

    # Count successful requests in window
    count = db.execute(
        "SELECT COUNT(*) FROM rate_limit_tracker "
        "WHERE site_name = ? AND request_timestamp >= ? "
        "AND status = 'success'",
        (site_name, window_start.isoformat())
    )

    if count >= max_requests:
        # Calculate wait time
        oldest = db.execute(
            "SELECT request_timestamp FROM rate_limit_tracker "
            "WHERE site_name = ? ORDER BY request_timestamp ASC LIMIT 1",
            (site_name,)
        )
        expire_time = oldest + timedelta(seconds=period_seconds)
        wait_seconds = (expire_time - now).total_seconds()

        return {'allowed': False, 'wait_seconds': wait_seconds}

    return {'allowed': True, 'wait_seconds': 0}
```

### 7.2 自動待機ロジック

```python
def wait_if_needed(self, site_name: str):
    check = self.can_make_request(site_name)

    if not check['allowed']:
        wait_time = check['wait_seconds']
        logger.warning(f"Rate limit reached. Waiting {wait_time}s...")
        time.sleep(wait_time)
        return True

    return False
```

---

## 8. スクレイピング実装

### 8.1 BaseScraper (基底クラス)

```python
class BaseScraper(ABC):
    def __init__(self, site_name, base_url, db_path, logger):
        self.site_name = site_name
        self.rate_limiter = RateLimiter(db_path, logger)
        self.max_retries = 3
        self.page_timeout = 30

    def setup_driver(self):
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        self.driver = webdriver.Chrome(options=options)

    def safe_get(self, url: str) -> bool:
        try:
            start_time = time.time()
            self.driver.get(url)
            response_time = int((time.time() - start_time) * 1000)

            self.rate_limiter.record_request(
                self.site_name, 'success', response_time
            )
            return True
        except TimeoutException:
            self.rate_limiter.record_request(
                self.site_name, 'timeout'
            )
            raise

    def scrape(self) -> List[Dict]:
        try:
            self.setup_driver()
            self.rate_limiter.wait_if_needed(self.site_name)
            properties = self._scrape_implementation()
            return properties
        finally:
            self.teardown_driver()

    @abstractmethod
    def _scrape_implementation(self) -> List[Dict]:
        pass
```

---

## 9. AI分析エンジン

### 9.1 スコアリングロジック

```python
class PropertyScorer:
    def calculate_score(self, property_data: dict) -> dict:
        scores = {}

        # 1. 広さスコア (0-25点)
        area_sqm = property_data.get('area_sqm', 0)
        ideal_area = 5000
        scores['area_score'] = min(25, (area_sqm / ideal_area) * 25)

        # 2. 隣近所配慮スコア (0-20点) ★重要★
        neighbor_distance = property_data.get('nearest_house_distance_m', 0)
        if neighbor_distance >= 500:
            scores['neighbor_score'] = 20
        elif neighbor_distance >= 300:
            scores['neighbor_score'] = 15
        else:
            scores['neighbor_score'] = 10

        # 3. 道路適性スコア (0-20点) ★重要★
        road_width = property_data.get('road_width_m', 0)
        if road_width >= 4.5:
            scores['road_score'] = 20
        elif road_width >= 3.5:
            scores['road_score'] = 15
        else:
            scores['road_score'] = 10

        # 4. 生活利便性スコア (0-15点)
        conbini_km = property_data.get('nearest_conbini_km', 999)
        scores['convenience_score'] = 15 if conbini_km < 10 else 10

        # 5. 景観スコア (0-10点)
        scores['scenery_score'] = 10

        # 6. アクセススコア (0-10点)
        station_km = property_data.get('nearest_station_km', 999)
        scores['access_score'] = 10 if station_km < 10 else 5

        # 合計
        scores['total_score'] = sum(scores.values())
        scores['confidence'] = 0.85

        return scores
```

---

## 10. ブログ生成システム

### 10.1 日次Markdown生成

```python
class DailyPostGenerator:
    def generate_post(self, date: str, properties: List[Dict], 
                     stats: Dict) -> Path:
        template = self._get_template()

        context = {
            'date': date,
            'total_properties': stats.get('total', 0),
            'new_properties': stats.get('new', 0),
            'avg_score': stats.get('avg_score', 0),
            'top_properties': properties[:10]
        }

        markdown = template.render(**context)

        post_path = self.posts_dir / f"{date}.md"
        with open(post_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        return post_path
```

### 10.2 Jinja2テンプレート

```jinja2
---
title: "{{ date }} キャンプ適地レポート"
date: {{ date }}T06:00:00+09:00
tags: ["daily", "{{ date[:4] }}"]
---

## 📊 本日の統計

- 総物件数: {{ total_properties }}件
- 新規物件: {{ new_properties }}件
- 平均スコア: {{ avg_score|round(1) }}点

## 🏆 TOP 10物件

{% for property in top_properties %}
### {{ loop.index }}. {{ property.name }}

- 📍 所在地: {{ property.location }}
- 📐 面積: {{ property.area_sqm }}m²
- 💰 価格: {{ property.price_formatted }}
- ⭐ スコア: **{{ property.score }}/100点**

---
{% endfor %}
```

---

## 11. Hugo静的サイト

### 11.1 config.toml

```toml
baseURL = "https://username.github.io/seccamp/"
languageCode = "ja"
title = "SECCAMP - キャンプ適地レポート"
theme = "seccamp-theme"

[params]
  description = "AI自動分析による日次レポート"
  author = "SECCAMP Bot"

[menu]
  [[menu.main]]
    name = "ホーム"
    url = "/"
  [[menu.main]]
    name = "記事一覧"
    url = "/posts/"
```

### 11.2 Hugo Build

```python
class HugoBuilder:
    def build(self) -> bool:
        result = subprocess.run(
            ['hugo', '--minify'],
            cwd=self.site_dir,
            capture_output=True,
            timeout=60
        )

        if result.returncode == 0:
            logger.info("Hugo build successful")
            return True
        else:
            logger.error(f"Hugo build failed: {result.stderr}")
            return False
```

---

## 12. Git自動公開

### 12.1 GitPusher

```python
class GitPusher:
    def commit_and_push(self, message: str) -> Optional[str]:
        try:
            # Add files
            subprocess.run(['git', 'add', 'public/'], cwd=self.repo_dir)
            subprocess.run(['git', 'add', 'content/posts/'], cwd=self.repo_dir)

            # Commit
            subprocess.run(['git', 'commit', '-m', message], cwd=self.repo_dir)

            # Get commit hash
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.repo_dir,
                capture_output=True,
                text=True
            )
            commit_hash = result.stdout.strip()

            # Push
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=self.repo_dir)

            return commit_hash
        except Exception as e:
            logger.error(f"Git push failed: {e}")
            return None
```

---

## 13. エラーハンドリング

### 13.1 リトライデコレータ

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=1, min=2, max=10))
def safe_get(url: str):
    driver.get(url)
```

### 13.2 例外処理

```python
try:
    properties = scraper.scrape()
except TimeoutException:
    logger.warning("Timeout, will retry...")
except WebDriverException as e:
    logger.error(f"WebDriver error: {e}")
finally:
    driver.quit()
```

---

## 14. GitHub Actions

### 14.1 Workflow設定

```yaml
name: SECCAMP Daily Batch

on:
  schedule:
    - cron: '0 21 * * *'  # 06:00 JST
  workflow_dispatch:

jobs:
  run-batch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker
        run: docker-compose build

      - name: Run batch
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: docker-compose run --rm seccamp --mode full

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./data/hugo_site/public
          publish_branch: gh-pages
```

---

## 15. 運用手順

### 15.1 初回セットアップ

```bash
# 1. Clone repository
git clone https://github.com/username/seccamp.git
cd seccamp

# 2. Create .env file
cp .env.example .env
# Edit .env with your GitHub token

# 3. Create data directory
mkdir -p data/hugo_site/content/posts

# 4. Initialize Hugo site
cd data/hugo_site
hugo new site . --force
cd ../..

# 5. Build Docker image
docker-compose build

# 6. First run
docker-compose up
```

### 15.2 日次実行

GitHub Actionsが自動的に毎朝06:00 JSTに実行します。

手動実行:
```bash
docker-compose up
```

### 15.3 ログ確認

```bash
# View latest log
tail -f data/logs/seccamp-$(date +%Y-%m-%d).log

# Check database
sqlite3 data/seccamp.db "SELECT * FROM scraping_logs ORDER BY started_at DESC LIMIT 10"
```

---

## 16. 付録

### 16.1 対象不動産サイト

| No. | サイト名 | URL | レート制限 |
|-----|---------|-----|-----------|
| 1 | アットホーム | athome.co.jp | 60 req/5min |
| 2 | SUUMO | suumo.jp | 30 req/5min |
| 3 | 家いちば | ieichiba.com | 20 req/5min |
| 4 | ゼロ円物件 | zero.estate | 10 req/5min |
| 5 | ジモティー | jmty.jp | 20 req/5min |

### 16.2 環境変数

```bash
# .env file
LOG_LEVEL=INFO
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=username/seccamp
GITHUB_USER=Your Name
GITHUB_EMAIL=your@email.com
HUGO_BASE_URL=https://username.github.io/seccamp/
```

### 16.3 トラブルシューティング

| 問題 | 原因 | 解決策 |
|------|------|--------|
| Chrome driver error | バージョン不一致 | docker-compose build --no-cache |
| Rate limit exceeded | レート制限超過 | DBで period_seconds 調整 |
| Hugo build failed | テンプレートエラー | ログ確認、構文チェック |
| Git push failed | 認証エラー | GITHUB_TOKEN 確認 |

### 16.4 パフォーマンスチューニング

```python
# Disable images for faster scraping
chrome_options.add_argument('--disable-images')
chrome_options.add_argument('--blink-settings=imagesEnabled=false')

# Adjust timeouts
self.page_timeout = 30
self.element_timeout = 10
```

---

## まとめ

本仕様書に基づき実装することで、完全自動化されたプライベートキャンプ場物件検索システムが構築できます。

### 主要な特徴

✅ Docker完全隔離環境  
✅ SQLiteリアルタイムレート制限  
✅ 日次Markdownブログ自動生成  
✅ Hugo静的サイトビルド  
✅ GitHub Pages自動デプロイ  
✅ 堅牢なエラーハンドリング  
✅ GitHub Actions自動実行  

### 次のステップ

1. 本仕様書に基づいてコード実装
2. Dockerイメージビルド
3. ローカルテスト実行
4. GitHub Actionsセットアップ
5. 本番運用開始

---

**作成者:** SECCAMP開発チーム  
**最終更新:** 2025年12月24日 19:35 JST  
**バージョン:** 3.0 (Complete)  
**ライセンス:** MIT  
**問い合わせ:** seccamp@example.com
