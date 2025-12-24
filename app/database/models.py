"""SQLAlchemy database models for SECCAMP."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint as SQLCheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============================================
# Rate Limiting Tables
# ============================================

class RateLimit(Base):
    """Rate limit configuration per site."""
    __tablename__ = "rate_limits"

    limit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    max_requests: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    period_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    concurrent_limit: Mapped[int] = mapped_column(Integer, default=1)
    retry_after_seconds: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RateLimitTracker(Base):
    """Request history for rate limiting."""
    __tablename__ = "rate_limit_tracker"

    tracker_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_name: Mapped[str] = mapped_column(String, nullable=False)
    request_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        SQLCheckConstraint("status IN ('success', 'failed', 'timeout')", name="ck_tracker_status"),
        Index("idx_tracker_site_time", "site_name", "request_timestamp"),
        Index("idx_tracker_cache", "from_cache", "request_timestamp"),
    )


# ============================================
# Caching Tables
# ============================================

class CacheEntry(Base):
    """URL index for cache lookup."""
    __tablename__ = "cache_entries"

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    url_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    source_site: Mapped[str] = mapped_column(String, nullable=False)
    page_type: Mapped[str] = mapped_column(String, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    first_cached_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cache_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scraped_pages_cache.cache_id", ondelete="CASCADE"))

    __table_args__ = (
        SQLCheckConstraint("page_type IN ('list', 'detail', 'image')", name="ck_cache_page_type"),
        Index("idx_cache_url_hash", "url_hash"),
        Index("idx_cache_normalized_url", "normalized_url"),
        Index("idx_cache_expires", "expires_at", "is_valid"),
        Index("idx_cache_site_type", "source_site", "page_type"),
    )


class ScrapedPageCache(Base):
    """Content storage for cached pages."""
    __tablename__ = "scraped_pages_cache"

    cache_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    http_headers: Mapped[Optional[str]] = mapped_column(Text)
    raw_html: Mapped[Optional[str]] = mapped_column(Text)
    raw_html_size: Mapped[Optional[int]] = mapped_column(Integer)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_data: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    scraper_version: Mapped[str] = mapped_column(String, default="1.0")
    user_agent: Mapped[Optional[str]] = mapped_column(String)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scraping_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    parsing_success: Mapped[bool] = mapped_column(Boolean, default=True)
    parsing_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_cache_content_hash", "content_hash"),
        Index("idx_cache_scraped_at", "scraped_at"),
    )


class CacheStats(Base):
    """Daily cache performance statistics."""
    __tablename__ = "cache_stats"

    stat_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stat_date: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    cache_misses: Mapped[int] = mapped_column(Integer, default=0)
    cache_expired: Mapped[int] = mapped_column(Integer, default=0)
    cache_invalidated: Mapped[int] = mapped_column(Integer, default=0)
    bandwidth_saved_mb: Mapped[float] = mapped_column(Float, default=0)
    time_saved_seconds: Mapped[float] = mapped_column(Float, default=0)
    total_cache_size_mb: Mapped[float] = mapped_column(Float, default=0)
    total_cache_entries: Mapped[int] = mapped_column(Integer, default=0)
    entries_cleaned: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_stats_date", "stat_date"),
    )


# ============================================
# Property Tables
# ============================================

class Property(Base):
    """Master property data."""
    __tablename__ = "properties"

    property_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source
    source_site: Mapped[str] = mapped_column(String, nullable=False)
    source_property_id: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    detail_page_cache_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scraped_pages_cache.cache_id"))

    # Basic Info
    property_name: Mapped[Optional[str]] = mapped_column(String)
    location_pref: Mapped[str] = mapped_column(String, nullable=False)
    location_city: Mapped[str] = mapped_column(String, nullable=False)
    location_detail: Mapped[Optional[str]] = mapped_column(Text)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    # Size & Price
    area_sqm: Mapped[Optional[int]] = mapped_column(Integer)
    area_tsubo: Mapped[Optional[float]] = mapped_column(Float)
    price_yen: Mapped[Optional[int]] = mapped_column(Integer)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)

    # Property Type
    property_type: Mapped[Optional[str]] = mapped_column(String)
    building_age: Mapped[Optional[int]] = mapped_column(Integer)

    # Access
    road_width_m: Mapped[Optional[float]] = mapped_column(Float)
    access_status: Mapped[Optional[str]] = mapped_column(String)
    nearest_station_km: Mapped[Optional[float]] = mapped_column(Float)

    # Location
    altitude_m: Mapped[Optional[int]] = mapped_column(Integer)
    slope_percent: Mapped[Optional[float]] = mapped_column(Float)
    surrounding_env: Mapped[Optional[str]] = mapped_column(String)
    population_density: Mapped[Optional[float]] = mapped_column(Float)
    nearest_house_distance_m: Mapped[Optional[int]] = mapped_column(Integer)

    # Utilities
    water_available: Mapped[bool] = mapped_column(Boolean, default=False)
    electric_available: Mapped[bool] = mapped_column(Boolean, default=False)
    telecom_coverage: Mapped[Optional[str]] = mapped_column(String)

    # Regulations
    agricultural_land: Mapped[bool] = mapped_column(Boolean, default=False)
    buildable: Mapped[bool] = mapped_column(Boolean, default=True)
    urban_planning_zone: Mapped[Optional[str]] = mapped_column(String)

    # Convenience
    nearest_conbini_km: Mapped[Optional[float]] = mapped_column(Float)
    nearest_supermarket_km: Mapped[Optional[float]] = mapped_column(Float)
    nearest_hospital_km: Mapped[Optional[float]] = mapped_column(Float)

    # Score
    campsite_score: Mapped[float] = mapped_column(Float, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)

    # Metadata
    listing_date: Mapped[Optional[str]] = mapped_column(String)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_site", "source_property_id"),
        Index("idx_properties_score", "campsite_score", "is_active"),
        Index("idx_properties_site", "source_site", "is_active"),
        Index("idx_properties_cache", "detail_page_cache_id"),
    )


class PropertyImage(Base):
    """Property images."""
    __tablename__ = "property_images"

    image_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.property_id", ondelete="CASCADE"), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_type: Mapped[str] = mapped_column(String)
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    image_cache_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scraped_pages_cache.cache_id"))
    scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        SQLCheckConstraint("image_type IN ('exterior', 'interior', 'map', 'other')", name="ck_image_type"),
        Index("idx_images_property", "property_id", "order_num"),
    )


# ============================================
# AI Scoring Tables
# ============================================

class AIScore(Base):
    """AI analysis scores for properties."""
    __tablename__ = "ai_scores"

    score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.property_id", ondelete="CASCADE"), nullable=False)

    area_score: Mapped[float] = mapped_column(Float, default=0)
    neighbor_score: Mapped[float] = mapped_column(Float, default=0)
    road_score: Mapped[float] = mapped_column(Float, default=0)
    convenience_score: Mapped[float] = mapped_column(Float, default=0)
    scenery_score: Mapped[float] = mapped_column(Float, default=0)
    access_score: Mapped[float] = mapped_column(Float, default=0)

    total_score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)

    analysis_details: Mapped[Optional[str]] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    model_version: Mapped[str] = mapped_column(String, default="1.0")

    __table_args__ = (
        SQLCheckConstraint("area_score >= 0 AND area_score <= 25", name="ck_area_score"),
        SQLCheckConstraint("neighbor_score >= 0 AND neighbor_score <= 20", name="ck_neighbor_score"),
        SQLCheckConstraint("road_score >= 0 AND road_score <= 20", name="ck_road_score"),
        SQLCheckConstraint("convenience_score >= 0 AND convenience_score <= 15", name="ck_convenience_score"),
        SQLCheckConstraint("scenery_score >= 0 AND scenery_score <= 10", name="ck_scenery_score"),
        SQLCheckConstraint("access_score >= 0 AND access_score <= 10", name="ck_access_score"),
        SQLCheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_total_score"),
        SQLCheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_confidence"),
        Index("idx_scores_total", "total_score"),
        Index("idx_scores_property", "property_id"),
    )


# ============================================
# Logging Tables
# ============================================

class ScrapingLog(Base):
    """Scraping session logs."""
    __tablename__ = "scraping_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_date: Mapped[str] = mapped_column(String, nullable=False)
    source_site: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, nullable=False)

    # Results
    properties_found: Mapped[int] = mapped_column(Integer, default=0)
    properties_new: Mapped[int] = mapped_column(Integer, default=0)
    properties_updated: Mapped[int] = mapped_column(Integer, default=0)

    # Cache Statistics
    pages_cached: Mapped[int] = mapped_column(Integer, default=0)
    cache_hits: Mapped[int] = mapped_column(Integer, default=0)
    cache_misses: Mapped[int] = mapped_column(Integer, default=0)

    # Errors
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    error_messages: Mapped[Optional[str]] = mapped_column(Text)

    execution_time_sec: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        SQLCheckConstraint("status IN ('running', 'success', 'failed', 'partial')", name="ck_log_status"),
        Index("idx_logs_date", "batch_date", "source_site"),
    )


class DailyBlog(Base):
    """Daily blog metadata."""
    __tablename__ = "daily_blogs"

    blog_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blog_date: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    markdown_path: Mapped[str] = mapped_column(String, nullable=False)
    properties_featured: Mapped[int] = mapped_column(Integer, default=0)
    total_properties: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[Optional[float]] = mapped_column(Float)
    max_score: Mapped[Optional[float]] = mapped_column(Float)
    hugo_built_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    git_commit_hash: Mapped[Optional[str]] = mapped_column(String)
    published_url: Mapped[Optional[str]] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_blogs_date", "blog_date"),
    )
