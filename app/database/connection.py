"""Neon PostgreSQL connection manager for SECCAMP."""
import os
import logging
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Neon PostgreSQL connection manager.

    Handles connection to Neon PostgreSQL serverless database.
    Uses NullPool since Neon has built-in connection pooling.
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL connection URL. If None, reads from DATABASE_URL env var.
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError(
                "DATABASE_URL not set. Please set the DATABASE_URL environment variable "
                "or pass it to the constructor."
            )

        # Neon uses connection pooling, so we use NullPool to avoid double pooling
        self.engine = create_engine(
            self.database_url,
            poolclass=NullPool,
            echo=False,
            connect_args={
                "connect_timeout": 10,
                "options": "-c timezone=utc",
            },
        )

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info("Connected to Neon PostgreSQL")

    @contextmanager
    def get_session(self) -> Session:
        """
        Get database session with automatic cleanup.

        Yields:
            Session: SQLAlchemy session

        Example:
            with db.get_session() as session:
                session.query(Property).all()
        """
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

    def get_session_no_ctx(self) -> Session:
        """
        Get database session without context manager.

        Returns:
            Session: SQLAlchemy session (caller must close/commit)

        Example:
            session = db.get_session_no_ctx()
            try:
                ...
                session.commit()
            finally:
                session.close()
        """
        return self.SessionLocal()

    def execute_raw(self, query: str, params: Optional[dict] = None):
        """
        Execute raw SQL query.

        Args:
            query: SQL query string
            params: Optional parameters for query

        Returns:
            Result object
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                row = result.fetchone()
                if row and row[0] == 1:
                    logger.info("Neon connection test successful")
                    return True
                return False
        except Exception as e:
            logger.error(f"Neon connection test failed: {e}")
            return False

    def initialize_schema(self) -> bool:
        """
        Initialize database schema from SQL file.

        Returns:
            True if initialization successful, False otherwise
        """
        from pathlib import Path

        # SQL file is in app/ directory
        sql_file = Path(__file__).parent.parent / "init_database_neon.sql"
        if not sql_file.exists():
            logger.warning(f"SQL init file not found at {sql_file}")
            return False

        try:
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_script = f.read()

            with self.engine.connect() as conn:
                # Split and execute statements
                # PostgreSQL can handle multiple statements in one execute
                conn.execute(text(sql_script))
                conn.commit()

            logger.info("Database schema initialized from SQL file")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            return False

    def is_initialized(self) -> bool:
        """
        Check if database schema is initialized.

        Returns:
            True if rate_limits table exists, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'rate_limits')"
                ))
                row = result.fetchone()
                return row and row[0] is True
        except Exception as e:
            logger.error(f"Failed to check initialization: {e}")
            return False


# Global singleton instance
_db_instance: Optional[DatabaseConnection] = None


def get_db(database_url: Optional[str] = None) -> DatabaseConnection:
    """
    Get global database connection singleton.

    Args:
        database_url: Optional database URL (only used on first call)

    Returns:
        DatabaseConnection instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseConnection(database_url)
    return _db_instance


def reset_db():
    """Reset global database connection (mainly for testing)."""
    global _db_instance
    _db_instance = None
