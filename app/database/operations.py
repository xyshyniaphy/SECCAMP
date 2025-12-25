"""Database operations for SECCAMP (Neon PostgreSQL)."""
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, text, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base, Property, AIScore, ScrapingLog, DailyBlog


logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for SECCAMP using Neon PostgreSQL."""

    # TTL values for cache
    TTL_LIST_PAGE = 6 * 3600  # 6 hours
    TTL_DETAIL_PAGE = 7 * 86400  # 7 days
    TTL_IMAGE = 30 * 86400  # 30 days

    def __init__(self, database_url: str):
        """
        Initialize database manager.

        Args:
            database_url: PostgreSQL connection URL (e.g., from DATABASE_URL env var)
        """
        self.database_url = database_url

        # Create engine with NullPool (Neon has built-in pooling)
        self.engine = create_engine(
            self.database_url,
            poolclass=NullPool,
            echo=False,
            connect_args={
                "connect_timeout": 10,
                "options": "-c timezone=utc",
            },
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Ensure database schema is initialized."""
        # Check if tables exist
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'rate_limits')"
            ))
            exists = result.fetchone()[0]

            if not exists:
                logger.info("Database not initialized, creating schema")
                self._initialize_from_sql()

    def _initialize_from_sql(self) -> None:
        """Initialize database from SQL file."""
        # SQL file is in app/ directory, we're in app/database/
        sql_file = Path(__file__).parent.parent / "init_database_neon.sql"
        if not sql_file.exists():
            logger.warning(f"SQL init file not found at {sql_file}")
            return

        with open(sql_file, "r", encoding="utf-8") as f:
            sql_script = f.read()

        with self.engine.connect() as conn:
            conn.execute(text(sql_script))
            conn.commit()

        logger.info("Database initialized from SQL file")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # ============================================
    # Property Operations
    # ============================================

    def upsert_property(self, session: Session, property_data: Dict[str, Any]) -> int:
        """
        Insert or update a property.

        Returns:
            property_id
        """
        # Check if exists
        stmt = select(Property).where(
            Property.source_site == property_data["source_site"],
            Property.source_property_id == property_data["source_property_id"],
        )
        existing = session.execute(stmt).scalar_one_or_none()

        now = datetime.utcnow()

        if existing:
            # Update
            for key, value in property_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.last_seen_at = now
            session.flush()
            return existing.property_id
        else:
            # Insert
            property_data["scraped_at"] = now
            property_data["last_seen_at"] = now
            new_property = Property(**property_data)
            session.add(new_property)
            session.flush()
            return new_property.property_id

    def get_property_by_source(self, session: Session, source_site: str, source_id: str) -> Optional[Property]:
        """Get property by source site and ID."""
        stmt = select(Property).where(
            Property.source_site == source_site,
            Property.source_property_id == source_id,
            Property.is_active == True,
        )
        return session.execute(stmt).scalar_one_or_none()

    def get_top_properties(self, session: Session, limit: int = 50) -> List[Property]:
        """Get top properties by score."""
        stmt = (
            select(Property)
            .where(Property.is_active == True)
            .order_by(Property.campsite_score.desc())
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())

    def deactivate_old_properties(self, session: Session, days: int = 30) -> int:
        """Deactivate properties not seen in specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = (
            update(Property)
            .where(Property.last_seen_at < cutoff)
            .where(Property.is_active == True)
            .values(is_active=False)
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount

    # ============================================
    # AI Score Operations
    # ============================================

    def save_ai_score(self, session: Session, property_id: int, score_data: Dict[str, Any]) -> int:
        """Save or update AI score for a property."""
        stmt = select(AIScore).where(AIScore.property_id == property_id)
        existing = session.execute(stmt).scalar_one_or_none()

        score_data["property_id"] = property_id
        score_data["calculated_at"] = datetime.utcnow()

        if existing:
            for key, value in score_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            session.flush()
            return existing.score_id
        else:
            new_score = AIScore(**score_data)
            session.add(new_score)
            session.flush()
            return new_score.score_id

    # ============================================
    # Scraping Log Operations
    # ============================================

    def create_scraping_log(self, session: Session, batch_date: str, source_site: str) -> int:
        """Create a new scraping log entry."""
        log = ScrapingLog(
            batch_date=batch_date,
            source_site=source_site,
            started_at=datetime.utcnow(),
            status="running",
        )
        session.add(log)
        session.flush()
        return log.log_id

    def update_scraping_log(
        self,
        session: Session,
        log_id: int,
        status: str,
        properties_found: int = 0,
        properties_new: int = 0,
        properties_updated: int = 0,
        cache_hits: int = 0,
        cache_misses: int = 0,
        pages_cached: int = 0,
        errors_count: int = 0,
        error_messages: Optional[str] = None,
    ) -> None:
        """Update scraping log entry."""
        log = session.get(ScrapingLog, log_id)
        if log:
            log.status = status
            log.completed_at = datetime.utcnow()
            log.properties_found = properties_found
            log.properties_new = properties_new
            log.properties_updated = properties_updated
            log.cache_hits = cache_hits
            log.cache_misses = cache_misses
            log.pages_cached = pages_cached
            log.errors_count = errors_count
            log.error_messages = error_messages

            # Calculate execution time
            if log.completed_at:
                log.execution_time_sec = (log.completed_at - log.started_at).total_seconds()

        session.commit()

    # ============================================
    # Daily Blog Operations
    # ============================================

    def save_daily_blog(
        self,
        session: Session,
        blog_date: str,
        markdown_path: Path,
        properties_featured: int,
        total_properties: int,
        avg_score: float,
        max_score: float,
    ) -> int:
        """Save daily blog metadata."""
        blog = DailyBlog(
            blog_date=blog_date,
            markdown_path=str(markdown_path),
            properties_featured=properties_featured,
            total_properties=total_properties,
            avg_score=avg_score,
            max_score=max_score,
            generated_at=datetime.utcnow(),
        )
        session.add(blog)
        session.flush()
        return blog.blog_id

    # ============================================
    # Cache Maintenance
    # ============================================

    def cleanup_expired_cache(self) -> Dict[str, int]:
        """Clean up expired cache entries."""
        with self.engine.connect() as conn:
            # Mark expired as invalid
            result = conn.execute(text(
                """
                UPDATE cache_entries
                SET is_valid = FALSE
                WHERE expires_at < CURRENT_TIMESTAMP AND is_valid = TRUE
                """
            ))
            invalidated = result.rowcount

            # Delete orphaned content
            result = conn.execute(text(
                """
                DELETE FROM scraped_pages_cache
                WHERE cache_id NOT IN (
                    SELECT DISTINCT cache_id
                    FROM cache_entries
                    WHERE is_valid = TRUE AND cache_id IS NOT NULL
                )
                """
            ))
            deleted = result.rowcount

            conn.commit()

        logger.info(f"Cache cleanup: invalidated={invalidated}, deleted={deleted}")
        return {"invalidated": invalidated, "deleted": deleted}

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.engine.connect() as conn:
            # Total entries
            result = conn.execute(text(
                "SELECT COUNT(*) FROM cache_entries WHERE is_valid = TRUE"
            ))
            total = result.fetchone()[0]

            # Total size
            result = conn.execute(text(
                """
                SELECT COALESCE(SUM(raw_html_size) / 1024.0 / 1024.0, 0)
                FROM scraped_pages_cache spc
                JOIN cache_entries ce ON spc.cache_id = ce.cache_id
                WHERE ce.is_valid = TRUE
                """
            ))
            size = result.fetchone()[0]

            # Hit stats today
            today = date.today()
            result = conn.execute(text(
                """
                SELECT
                    COALESCE(SUM(cache_hits), 0) as total_hits
                FROM cache_entries
                WHERE DATE(last_accessed_at) = :today
                """
            ), {"today": today})
            hits = result.fetchone()[0]

        return {
            "total_entries": total,
            "total_size_mb": round(size, 2),
            "today_hits": hits,
        }

    # ============================================
    # Health Check
    # ============================================

    def health_check(self) -> Dict[str, Any]:
        """Perform database health check."""
        tables = [
            "rate_limits", "rate_limit_tracker", "cache_entries", "scraped_pages_cache",
            "cache_stats", "properties", "property_images", "ai_scores", "scraping_logs", "daily_blogs"
        ]

        counts = {}
        with self.engine.connect() as conn:
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    counts[table] = result.fetchone()[0]
                except Exception:
                    counts[table] = None  # Table doesn't exist

        return {
            "database": "Neon PostgreSQL",
            "url": self.database_url.split("@")[-1] if "@" in self.database_url else "unknown",
            "tables": counts
        }
