"""
Tests for DatabaseManager and database operations.
"""
import pytest
from datetime import datetime
from database import DatabaseManager
from database.models import Property, AIScore, ScrapingLog, DailyBlog


@pytest.mark.database
@pytest.mark.integration
class TestDatabaseManager:
    """Test suite for DatabaseManager class."""

    def test_init_database_manager(self, db_manager):
        """Test DatabaseManager initialization."""
        assert db_manager is not None
        assert db_manager.database_url is not None
        assert db_manager.engine is not None
        assert db_manager.SessionLocal is not None

    def test_get_session(self, db_manager):
        """Test getting a database session."""
        session = db_manager.get_session()

        assert session is not None
        session.close()

    def test_health_check(self, db_manager):
        """Test health check method."""
        result = db_manager.health_check()

        assert result is True

    def test_upsert_property_new(self, db_manager, db_session, sample_property_data):
        """Test inserting a new property."""
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        assert property_id is not None
        assert property_id > 0

        # Verify it was saved
        saved = db_session.get(Property, property_id)
        assert saved is not None
        assert saved.source_site == sample_property_data["source_site"]
        assert saved.source_property_id == sample_property_data["source_property_id"]
        assert saved.title == sample_property_data["title"]

    def test_upsert_property_update(self, db_manager, db_session, sample_property_data):
        """Test updating an existing property."""
        # Insert first
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Update with new data
        updated_data = sample_property_data.copy()
        updated_data["title"] = "更新後のタイトル"
        updated_data["price_yen"] = 2000000

        updated_id = db_manager.upsert_property(db_session, updated_data)
        db_session.commit()

        # Should be same ID
        assert updated_id == property_id

        # Verify updates
        saved = db_session.get(Property, property_id)
        assert saved.title == "更新後のタイトル"
        assert saved.price_yen == 2000000

    def test_get_property_by_source(self, db_manager, db_session, sample_property_data):
        """Test retrieving property by source."""
        # Insert property
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Retrieve
        found = db_manager.get_property_by_source(
            db_session,
            sample_property_data["source_site"],
            sample_property_data["source_property_id"]
        )

        assert found is not None
        assert found.property_id == property_id
        assert found.title == sample_property_data["title"]

    def test_get_property_by_source_not_found(self, db_manager, db_session):
        """Test retrieving non-existent property."""
        found = db_manager.get_property_by_source(
            db_session,
            "non_existent_site",
            "non_existent_id"
        )

        assert found is None

    def test_get_top_properties_empty(self, db_manager, db_session):
        """Test getting top properties when database is empty."""
        top_props = db_manager.get_top_properties(db_session, limit=10)

        assert top_props == []

    def test_get_top_properties_with_data(self, db_manager, db_session, sample_property_data):
        """Test getting top properties with scores."""
        # Insert multiple properties with different scores
        for i in range(5):
            prop_data = sample_property_data.copy()
            prop_data["source_property_id"] = f"test_{i}"
            prop_data["campsite_score"] = 90 - i * 5  # 90, 85, 80, 75, 70
            db_manager.upsert_property(db_session, prop_data)

        db_session.commit()

        # Get top 3
        top_props = db_manager.get_top_properties(db_session, limit=3)

        assert len(top_props) == 3
        # Should be sorted by score descending
        assert top_props[0].campsite_score == 90
        assert top_props[1].campsite_score == 85
        assert top_props[2].campsite_score == 80

    def test_get_top_properties_active_only(self, db_manager, db_session, sample_property_data):
        """Test that only active properties are returned."""
        # Insert active property
        active_data = sample_property_data.copy()
        active_data["source_property_id"] = "active_1"
        active_data["campsite_score"] = 90
        active_data["is_active"] = True
        db_manager.upsert_property(db_session, active_data)

        # Insert inactive property
        inactive_data = sample_property_data.copy()
        inactive_data["source_property_id"] = "inactive_1"
        inactive_data["campsite_score"] = 95
        inactive_data["is_active"] = False
        db_manager.upsert_property(db_session, inactive_data)

        db_session.commit()

        top_props = db_manager.get_top_properties(db_session, limit=10)

        # Should only return active property (lower score)
        assert len(top_props) == 1
        assert top_props[0].campsite_score == 90

    def test_deactivate_old_properties(self, db_manager, db_session, sample_property_data):
        """Test deactivating properties not seen recently."""
        # Insert old property (simulated by setting last_seen_at)
        old_prop_data = sample_property_data.copy()
        old_prop_data["source_property_id"] = "old_1"
        old_prop_data["campsite_score"] = 80
        property_id = db_manager.upsert_property(db_session, old_prop_data)

        # Manually set last_seen_at to old date
        old_prop = db_session.get(Property, property_id)
        old_prop.last_seen_at = datetime(2020, 1, 1)
        db_session.commit()

        # Deactivate
        count = db_manager.deactivate_old_properties(db_session, days_threshold=30)
        db_session.commit()

        assert count >= 1

        # Verify deactivated
        deactivated = db_session.get(Property, property_id)
        assert deactivated.is_active is False

    def test_save_ai_score_new(self, db_manager, db_session, sample_property_data, sample_ai_score_data):
        """Test saving AI score for a property."""
        # First create property
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Save AI score
        score_id = db_manager.save_ai_score(db_session, property_id, sample_ai_score_data)
        db_session.commit()

        assert score_id is not None

        # Verify
        score = db_session.query(AIScore).filter_by(property_id=property_id).first()
        assert score is not None
        assert score.total_score == sample_ai_score_data["total_score"]
        assert score.area_score == sample_ai_score_data["area_score"]

    def test_save_ai_score_update(self, db_manager, db_session, sample_property_data, sample_ai_score_data):
        """Test updating existing AI score."""
        # Create property
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Save initial score
        score_id = db_manager.save_ai_score(db_session, property_id, sample_ai_score_data)
        db_session.commit()

        # Update score
        updated_score_data = sample_ai_score_data.copy()
        updated_score_data["total_score"] = 95.0
        updated_score_data["area_score"] = 30.0

        updated_score_id = db_manager.save_ai_score(db_session, property_id, updated_score_data)
        db_session.commit()

        # Should be same score_id
        assert updated_score_id == score_id

        # Verify update
        score = db_session.get(AIScore, score_id)
        assert score.total_score == 95.0
        assert score.area_score == 30.0

    def test_create_scraping_log(self, db_manager, db_session):
        """Test creating a scraping log entry."""
        log_id = db_manager.create_scraping_log(
            db_session,
            site_name="athome",
            status="running"
        )
        db_session.commit()

        assert log_id is not None

        # Verify
        log = db_session.get(ScrapingLog, log_id)
        assert log is not None
        assert log.site_name == "athome"
        assert log.status == "running"

    def test_update_scraping_log(self, db_manager, db_session):
        """Test updating a scraping log entry."""
        # Create log
        log_id = db_manager.create_scraping_log(
            db_session,
            site_name="athome",
            status="running"
        )
        db_session.commit()

        # Update
        db_manager.update_scraping_log(
            db_session,
            log_id,
            status="completed",
            properties_found=10,
            properties_saved=8
        )
        db_session.commit()

        # Verify
        log = db_session.get(ScrapingLog, log_id)
        assert log.status == "completed"
        assert log.properties_found == 10
        assert log.properties_saved == 8
        assert log.finished_at is not None

    def test_save_daily_blog_new(self, db_manager, db_session):
        """Test saving daily blog metadata."""
        blog_date = datetime(2024, 1, 15).date()

        blog_id = db_manager.save_daily_blog(
            db_session,
            blog_date=blog_date,
            post_path="/content/posts/2024-01-15.md",
            properties_count=50
        )
        db_session.commit()

        assert blog_id is not None

        # Verify
        blog = db_session.query(DailyBlog).filter_by(blog_date=blog_date).first()
        assert blog is not None
        assert blog.post_path == "/content/posts/2024-01-15.md"
        assert blog.properties_count == 50

    def test_save_daily_blog_update(self, db_manager, db_session):
        """Test updating existing daily blog."""
        blog_date = datetime(2024, 1, 15).date()

        # Create
        blog_id = db_manager.save_daily_blog(
            db_session,
            blog_date=blog_date,
            post_path="/content/posts/2024-01-15.md",
            properties_count=50
        )
        db_session.commit()

        # Update
        updated_blog_id = db_manager.save_daily_blog(
            db_session,
            blog_date=blog_date,
            post_path="/content/posts/2024-01-15-updated.md",
            properties_count=55
        )
        db_session.commit()

        # Should be same ID
        assert updated_blog_id == blog_id

        # Verify
        blog = db_session.get(DailyBlog, blog_id)
        assert blog.post_path == "/content/posts/2024-01-15-updated.md"
        assert blog.properties_count == 55

    def test_cleanup_expired_cache(self, db_manager, db_session):
        """Test cleanup of expired cache entries."""
        # This would test the cache cleanup functionality
        # Implementation depends on actual cache table structure
        result = db_manager.cleanup_expired_cache(db_session)

        assert isinstance(result, dict)

    def test_get_cache_stats(self, db_manager, db_session):
        """Test getting cache statistics."""
        stats = db_manager.get_cache_stats(db_session)

        assert isinstance(stats, dict)
        assert "total_entries" in stats

    def test_property_relationships(self, db_manager, db_session, sample_property_data, sample_ai_score_data):
        """Test relationships between Property and related models."""
        # Create property
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Add AI score
        score_id = db_manager.save_ai_score(db_session, property_id, sample_ai_score_data)
        db_session.commit()

        # Verify relationship
        prop = db_session.get(Property, property_id)
        assert prop.ai_score is not None
        assert prop.ai_score.score_id == score_id
        assert prop.ai_score.total_score == sample_ai_score_data["total_score"]

    def test_property_images(self, db_manager, db_session, sample_property_data):
        """Test adding images to a property."""
        # Create property
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Add images
        prop = db_session.get(Property, property_id)
        image1 = PropertyImage(
            property_id=property_id,
            image_url="https://example.com/image1.jpg",
            image_hash="hash1"
        )
        image2 = PropertyImage(
            property_id=property_id,
            image_url="https://example.com/image2.jpg",
            image_hash="hash2"
        )
        db_session.add_all([image1, image2])
        db_session.commit()

        # Verify
        prop = db_session.get(Property, property_id)
        assert len(prop.images) == 2

    def test_unique_constraint_per_source(self, db_manager, db_session, sample_property_data):
        """Test that unique constraint is enforced per source."""
        # Insert first property
        property_id1 = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Try to insert with same source + source_property_id
        property_id2 = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        # Should update, not create new
        assert property_id1 == property_id2

        # Verify only one exists
        props = db_session.query(Property).filter(
            Property.source_site == sample_property_data["source_site"],
            Property.source_property_id == sample_property_data["source_property_id"]
        ).all()

        assert len(props) == 1

    @pytest.mark.parametrize("field,value", [
        ("title", "テスト物件"),
        ("price_yen", 1500000),
        ("land_area_sqm", 1500.5),
        ("location_pref", "長野県"),
        ("is_active", True),
    ])
    def test_property_fields(self, db_manager, db_session, sample_property_data, field, value):
        """Test that property fields are stored correctly."""
        sample_property_data[field] = value
        property_id = db_manager.upsert_property(db_session, sample_property_data)
        db_session.commit()

        prop = db_session.get(Property, property_id)
        assert getattr(prop, field) == value

    def test_transaction_rollback(self, db_manager, db_session, sample_property_data):
        """Test that transactions can be rolled back."""
        initial_count = db_session.query(Property).count()

        # Insert property
        db_manager.upsert_property(db_session, sample_property_data)

        # Rollback
        db_session.rollback()

        # Count should be same
        final_count = db_session.query(Property).count()
        assert initial_count == final_count


@pytest.mark.database
class TestDatabaseModels:
    """Test suite for database ORM models."""

    def test_property_model_creation(self, db_session, sample_property_data):
        """Test creating Property directly."""
        prop = Property(**sample_property_data)
        db_session.add(prop)
        db_session.commit()

        assert prop.property_id is not None
        assert prop.title == sample_property_data["title"]

    def test_ai_score_model_creation(self, db_session, sample_property_data, sample_ai_score_data):
        """Test creating AIScore directly."""
        prop = Property(**sample_property_data)
        db_session.add(prop)
        db_session.flush()

        score_data = sample_ai_score_data.copy()
        score_data["property_id"] = prop.property_id
        score = AIScore(**score_data)
        db_session.add(score)
        db_session.commit()

        assert score.score_id is not None
        assert score.property_id == prop.property_id

    def test_scraping_log_model_creation(self, db_session):
        """Test creating ScrapingLog directly."""
        log = ScrapingLog(
            site_name="athome",
            status="running",
            started_at=datetime.utcnow()
        )
        db_session.add(log)
        db_session.commit()

        assert log.log_id is not None
        assert log.site_name == "athome"

    def test_daily_blog_model_creation(self, db_session):
        """Test creating DailyBlog directly."""
        blog = DailyBlog(
            blog_date=datetime(2024, 1, 15).date(),
            post_path="/content/posts/test.md",
            properties_count=10
        )
        db_session.add(blog)
        db_session.commit()

        assert blog.blog_id is not None
        assert blog.blog_date == datetime(2024, 1, 15).date()
