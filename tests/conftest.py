"""
Pytest configuration and shared fixtures for SECCAMP tests.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import pytest
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def temp_db_path(temp_dir):
    """Create a temporary database file path."""
    db_path = os.path.join(temp_dir, "test_seccamp.db")
    return db_path


@pytest.fixture
def memory_db():
    """Create an in-memory SQLite database for testing."""
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    yield connection
    connection.close()


@pytest.fixture
def init_sql_path():
    """Get the path to the database initialization SQL file."""
    return os.path.join(os.path.dirname(__file__), '..', 'app', 'init_database_complete.sql')


@pytest.fixture
def initialized_db(temp_db_path, init_sql_path):
    """
    Create a database initialized with the schema from init_database_complete.sql.
    """
    # Read the initialization SQL
    with open(init_sql_path, 'r', encoding='utf-8') as f:
        init_sql = f.read()

    # Create and initialize the database
    conn = sqlite3.connect(temp_db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Split and execute the SQL (handling multiple statements)
    statements = [s.strip() for s in init_sql.split(';') if s.strip()]
    for statement in statements:
        try:
            conn.execute(statement)
        except Exception as e:
            # Some statements might fail if they're already handled by SQLAlchemy
            pass

    conn.commit()
    conn.close()

    return temp_db_path


@pytest.fixture
def db_session(initialized_db):
    """
    Create a SQLAlchemy session for testing.
    """
    from database.models import Base

    # Create engine with the initialized database
    engine = create_engine(f'sqlite:///{initialized_db}', echo=False)

    # Create tables from models (in case SQL file missed any)
    Base.metadata.create_all(engine)

    # Create session
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def db_manager(initialized_db):
    """
    Create a DatabaseManager instance with a test database.
    """
    from database import DatabaseManager

    manager = DatabaseManager(initialized_db)
    yield manager

    # Cleanup is handled by temp_db_path fixture


@pytest.fixture
def sample_property_data():
    """
    Sample property data for testing.
    """
    return {
        "source_site": "athome",
        "source_property_id": "test_12345",
        "title": "テスト物件",
        "url": "https://example.com/property/12345",
        "price_yen": 1500000,
        "land_area_sqm": 1500.5,
        "building_area_sqm": 100.0,
        "building_year": 1990,
        "building_type": "平屋",
        "material": "木造",
        "location_pref": "長野県",
        "location_city": "茅野市",
        "location_town": "豊平",
        "latitude": 36.0595,
        "longitude": 138.1385,
        "description": "テスト用の物件説明です。",
        "is_active": True,
    }


@pytest.fixture
def sample_ai_score_data():
    """
    Sample AI score data for testing.
    """
    return {
        "area_score": 25.0,
        "neighbor_score": 20.0,
        "slope_score": 15.0,
        "access_score": 10.0,
        "utility_score": 10.0,
        "water_access_score": 5.0,
        "total_score": 85.0,
        "score_details": "良質な土地です。",
    }


@pytest.fixture
def mock_response():
    """
    Mock HTTP response for testing.
    """
    class MockResponse:
        def __init__(self, status_code=200, content=b'<html>test</html>', headers=None):
            self.status_code = status_code
            self.content = content
            self.text = content.decode('utf-8') if content else ''
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    return MockResponse


@pytest.fixture
def sample_html_content():
    """
    Sample HTML content for testing parsers.
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>テストページ</title>
        <meta charset="UTF-8">
    </head>
    <body>
        <div class="property-list">
            <div class="property-item">
                <h2 class="property-title">テスト物件1</h2>
                <span class="price">1,500万円</span>
                <span class="area">1,500㎡</span>
                <a href="/property/12345" class="detail-link">詳細</a>
            </div>
            <div class="property-item">
                <h2 class="property-title">テスト物件2</h2>
                <span class="price">2,000万円</span>
                <span class="area">2,000㎡</span>
                <a href="/property/67890" class="detail-link">詳細</a>
            </div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_sites_json(temp_dir):
    """
    Create a sample sites.json file for testing.
    """
    sites_data = {
        "athome": {
            "site_name": "athome",
            "display_name": "AtHome",
            "base_url": "https://www.athome.co.jp",
            "enabled": True,
            "rate_limit": {
                "max_requests": 60,
                "period_seconds": 300
            },
            "entry_urls": {
                "nagano": "https://www.athome.co.jp/kodate/chuko/nagano/list/"
            },
            "selectors": {
                "list_page": {
                    "property_container": ".property-list",
                    "property_item": ".property-item",
                    "title": ".property-title",
                    "url": ".detail-link"
                },
                "detail_page": {
                    "title": "h1.title",
                    "price": ".price",
                    "area": ".area"
                }
            }
        },
        "suumo": {
            "site_name": "suumo",
            "display_name": "SUUMO",
            "base_url": "https://suumo.jp",
            "enabled": False,
            "rate_limit": {
                "max_requests": 30,
                "period_seconds": 300
            }
        }
    }

    import json
    sites_path = os.path.join(temp_dir, "sites.json")
    with open(sites_path, 'w', encoding='utf-8') as f:
        json.dump(sites_data, f, ensure_ascii=False, indent=2)

    return sites_path


@pytest.fixture
def mock_driver():
    """
    Mock Selenium WebDriver for testing.
    """
    class MockWebDriver:
        def __init__(self):
            self.current_url = "https://example.com"
            self.page_source = "<html>test</html>"
            self._quit_called = False

        def get(self, url):
            self.current_url = url

        def find_element(self, by, value):
            class MockElement:
                pass
            return MockElement()

        def find_elements(self, by, value):
            return []

        def quit(self):
            self._quit_called = True

    return MockWebDriver


@pytest.fixture
def mock_cache_manager():
    """
    Mock CacheManager for testing scrapers.
    """
    class MockCacheManager:
        def __init__(self, db_path):
            self.db_path = db_path
            self.cache_hits = 0
            self.cache_misses = 0

        def get_cache(self, url_hash):
            self.cache_misses += 1
            return None

        def set_cache(self, url_hash, content, page_type, ttl_seconds):
            return True

        def get_stats(self):
            return {
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "total_entries": 0
            }

    return MockCacheManager


@pytest.fixture
def mock_rate_limiter():
    """
    Mock RateLimiter for testing scrapers.
    """
    class MockRateLimiter:
        def __init__(self, db_path):
            self.db_path = db_path
            self.wait_called = False

        def can_make_request(self, site_name):
            return True

        def wait_if_needed(self, site_name):
            self.wait_called = True

        def record_request(self, site_name):
            pass

        def get_stats(self, site_name):
            return {
                "requests_made": 0,
                "requests_remaining": 60,
                "reset_time": None
            }

    return MockRateLimiter


@pytest.fixture(scope="session")
def docker_compose_file():
    """
    Path to docker-compose file for integration tests.
    """
    return os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml')


# Pytest hooks
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "database: Tests that require database access")
    config.addinivalue_line("markers", "scraper: Tests that involve web scraping")


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add default markers.
    """
    for item in items:
        # Mark tests in test_database.py as database tests
        if "test_database" in str(item.fspath):
            item.add_marker(pytest.mark.database)
            item.add_marker(pytest.mark.integration)

        # Mark tests in test_scrapers.py as scraper tests
        if "test_scrapers" in str(item.fspath):
            item.add_marker(pytest.mark.scraper)
            item.add_marker(pytest.mark.slow)
