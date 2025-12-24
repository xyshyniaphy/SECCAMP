-- ============================================
-- SECCAMP SQLite Database Initialization
-- Version 4.0 - With Page-Level Caching
-- Date: 2025-12-24
-- ============================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================
-- 1. RATE LIMITING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS rate_limits (
    limit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT UNIQUE NOT NULL,
    max_requests INTEGER NOT NULL DEFAULT 60,
    period_seconds INTEGER NOT NULL DEFAULT 300,
    concurrent_limit INTEGER DEFAULT 1,
    retry_after_seconds INTEGER DEFAULT 60,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO rate_limits (site_name, max_requests, period_seconds) VALUES
('athome', 60, 300),
('suumo', 30, 300),
('ieichiba', 20, 300),
('zero_estate', 10, 300),
('jmty', 20, 300),
('homes', 30, 300),
('rakuten', 30, 300);

CREATE TABLE IF NOT EXISTS rate_limit_tracker (
    tracker_id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_name TEXT NOT NULL,
    request_timestamp TEXT NOT NULL,
    response_time_ms INTEGER,
    status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'timeout')),
    error_message TEXT,
    from_cache BOOLEAN DEFAULT 0,
    FOREIGN KEY (site_name) REFERENCES rate_limits(site_name)
);

CREATE INDEX IF NOT EXISTS idx_tracker_site_time 
ON rate_limit_tracker(site_name, request_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tracker_cache 
ON rate_limit_tracker(from_cache, request_timestamp DESC);

-- ============================================
-- 2. CACHING TABLES (NEW)
-- ============================================

CREATE TABLE IF NOT EXISTS cache_entries (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- URL Information
    original_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL UNIQUE,

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

    -- Foreign Keys
    cache_id INTEGER,
    FOREIGN KEY (cache_id) REFERENCES scraped_pages_cache(cache_id) ON DELETE CASCADE,
    FOREIGN KEY (source_site) REFERENCES rate_limits(site_name)
);

CREATE INDEX IF NOT EXISTS idx_cache_url_hash 
ON cache_entries(url_hash);

CREATE INDEX IF NOT EXISTS idx_cache_normalized_url 
ON cache_entries(normalized_url);

CREATE INDEX IF NOT EXISTS idx_cache_expires 
ON cache_entries(expires_at, is_valid);

CREATE INDEX IF NOT EXISTS idx_cache_site_type 
ON cache_entries(source_site, page_type);

CREATE TABLE IF NOT EXISTS scraped_pages_cache (
    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- HTTP Response
    http_status INTEGER NOT NULL,
    http_headers TEXT,

    -- Content Storage
    raw_html TEXT,
    raw_html_size INTEGER,
    is_compressed BOOLEAN DEFAULT 0,
    parsed_data TEXT,

    -- Content Hash
    content_hash TEXT NOT NULL,

    -- Metadata
    scraper_version TEXT DEFAULT '1.0',
    user_agent TEXT,
    scraped_at TEXT NOT NULL,
    scraping_duration_ms INTEGER,
    parsing_success BOOLEAN DEFAULT 1,
    parsing_error TEXT,

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cache_content_hash 
ON scraped_pages_cache(content_hash);

CREATE INDEX IF NOT EXISTS idx_cache_scraped_at 
ON scraped_pages_cache(scraped_at DESC);

CREATE TABLE IF NOT EXISTS cache_stats (
    stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date TEXT NOT NULL UNIQUE,

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

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stats_date 
ON cache_stats(stat_date DESC);

-- ============================================
-- 3. PROPERTY TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS properties (
    property_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Source
    source_site TEXT NOT NULL,
    source_property_id TEXT NOT NULL,
    source_url TEXT,
    detail_page_cache_id INTEGER,

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
    price_yen INTEGER,
    is_free BOOLEAN DEFAULT 0,

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
    water_available BOOLEAN DEFAULT 0,
    electric_available BOOLEAN DEFAULT 0,
    telecom_coverage TEXT,

    -- Regulations
    agricultural_land BOOLEAN DEFAULT 0,
    buildable BOOLEAN DEFAULT 1,
    urban_planning_zone TEXT,

    -- Convenience
    nearest_conbini_km REAL,
    nearest_supermarket_km REAL,
    nearest_hospital_km REAL,

    -- Score
    campsite_score REAL DEFAULT 0,
    confidence_score REAL DEFAULT 0,

    -- Metadata
    listing_date TEXT,
    scraped_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    UNIQUE(source_site, source_property_id),
    FOREIGN KEY (detail_page_cache_id) REFERENCES scraped_pages_cache(cache_id)
);

CREATE INDEX IF NOT EXISTS idx_properties_score 
ON properties(campsite_score DESC, is_active);

CREATE INDEX IF NOT EXISTS idx_properties_site 
ON properties(source_site, is_active);

CREATE INDEX IF NOT EXISTS idx_properties_cache 
ON properties(detail_page_cache_id);

CREATE TABLE IF NOT EXISTS property_images (
    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    image_url TEXT NOT NULL,
    image_type TEXT CHECK(image_type IN ('exterior', 'interior', 'map', 'other')),
    order_num INTEGER DEFAULT 0,
    image_cache_id INTEGER,
    scraped_at TEXT NOT NULL,
    FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE,
    FOREIGN KEY (image_cache_id) REFERENCES scraped_pages_cache(cache_id)
);

CREATE INDEX IF NOT EXISTS idx_images_property 
ON property_images(property_id, order_num);

-- ============================================
-- 4. AI SCORING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS ai_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,

    area_score REAL DEFAULT 0 CHECK(area_score >= 0 AND area_score <= 25),
    neighbor_score REAL DEFAULT 0 CHECK(neighbor_score >= 0 AND neighbor_score <= 20),
    road_score REAL DEFAULT 0 CHECK(road_score >= 0 AND road_score <= 20),
    convenience_score REAL DEFAULT 0 CHECK(convenience_score >= 0 AND convenience_score <= 15),
    scenery_score REAL DEFAULT 0 CHECK(scenery_score >= 0 AND scenery_score <= 10),
    access_score REAL DEFAULT 0 CHECK(access_score >= 0 AND access_score <= 10),

    total_score REAL DEFAULT 0 CHECK(total_score >= 0 AND total_score <= 100),
    confidence REAL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),

    analysis_details TEXT,

    calculated_at TEXT NOT NULL,
    model_version TEXT DEFAULT '1.0',

    FOREIGN KEY (property_id) REFERENCES properties(property_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scores_total 
ON ai_scores(total_score DESC);

CREATE INDEX IF NOT EXISTS idx_scores_property 
ON ai_scores(property_id);

-- ============================================
-- 5. LOGGING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS scraping_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_date TEXT NOT NULL,
    source_site TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
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
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_logs_date 
ON scraping_logs(batch_date DESC, source_site);

CREATE TABLE IF NOT EXISTS daily_blogs (
    blog_id INTEGER PRIMARY KEY AUTOINCREMENT,
    blog_date TEXT UNIQUE NOT NULL,
    markdown_path TEXT NOT NULL,
    properties_featured INTEGER DEFAULT 0,
    total_properties INTEGER DEFAULT 0,
    avg_score REAL,
    max_score REAL,
    hugo_built_at TEXT,
    git_commit_hash TEXT,
    published_url TEXT,
    generated_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_blogs_date 
ON daily_blogs(blog_date DESC);

-- ============================================
-- 6. VIEWS FOR CONVENIENCE
-- ============================================

CREATE VIEW IF NOT EXISTS v_top_properties AS
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
WHERE p.is_active = 1
ORDER BY s.total_score DESC;

CREATE VIEW IF NOT EXISTS v_cache_performance AS
SELECT 
    ce.source_site,
    ce.page_type,
    COUNT(*) as total_entries,
    SUM(CASE WHEN ce.is_valid = 1 THEN 1 ELSE 0 END) as valid_entries,
    SUM(ce.cache_hits) as total_hits,
    AVG(spc.raw_html_size) as avg_size_bytes,
    SUM(CASE WHEN spc.is_compressed = 1 THEN 1 ELSE 0 END) as compressed_count
FROM cache_entries ce
JOIN scraped_pages_cache spc ON ce.cache_id = spc.cache_id
GROUP BY ce.source_site, ce.page_type;

-- ============================================
-- 7. TRIGGERS FOR MAINTENANCE
-- ============================================

CREATE TRIGGER IF NOT EXISTS update_property_timestamp
AFTER UPDATE ON properties
FOR EACH ROW
BEGIN
    UPDATE properties SET updated_at = datetime('now') 
    WHERE property_id = NEW.property_id;
END;

CREATE TRIGGER IF NOT EXISTS update_cache_timestamp
AFTER UPDATE ON scraped_pages_cache
FOR EACH ROW
BEGIN
    UPDATE scraped_pages_cache SET updated_at = datetime('now') 
    WHERE cache_id = NEW.cache_id;
END;

-- ============================================
-- END OF INITIALIZATION
-- ============================================

SELECT 'Database initialized successfully!' AS status;
