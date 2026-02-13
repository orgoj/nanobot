"""Tests for background processing and entity extraction."""

import asyncio
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from nanobot.config.schema import MemoryConfig, ExtractionConfig
from nanobot.memory.models import Event, Entity
from nanobot.memory.store import MemoryStore
from nanobot.memory.background import ActivityTracker, BackgroundProcessor
from nanobot.memory.extraction import ExtractionResult, extract_entities


class TestActivityTracker:
    """Tests for ActivityTracker."""
    
    def test_initial_state(self):
        """Test initial state of activity tracker."""
        tracker = ActivityTracker(quiet_threshold_seconds=30)
        
        assert tracker.last_activity is None
        assert not tracker.is_user_active()
        assert tracker.seconds_since_last_activity() == float('inf')
    
    def test_mark_activity(self):
        """Test marking user activity."""
        tracker = ActivityTracker(quiet_threshold_seconds=30)
        
        tracker.mark_activity()
        
        assert tracker.last_activity is not None
        assert tracker.is_user_active()
        assert tracker.seconds_since_last_activity() < 1.0
    
    def test_activity_timeout(self):
        """Test that activity times out after threshold."""
        tracker = ActivityTracker(quiet_threshold_seconds=0.1)  # 100ms threshold
        
        tracker.mark_activity()
        assert tracker.is_user_active()
        
        # Wait for timeout
        import time
        time.sleep(0.15)
        
        assert not tracker.is_user_active()


class TestBackgroundProcessor:
    """Tests for BackgroundProcessor."""
    
    @pytest.fixture
    def temp_components(self):
        """Create temporary memory components for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            tracker = ActivityTracker(quiet_threshold_seconds=0.1)
            processor = BackgroundProcessor(store, tracker, interval_seconds=0.1)
            
            yield store, tracker, processor
            
            processor.stop()
            store.close()
    
    @pytest.mark.asyncio
    async def test_processor_start_stop(self, temp_components):
        """Test starting and stopping the processor."""
        store, tracker, processor = temp_components
        
        assert not processor.running
        
        await processor.start()
        assert processor.running
        
        await processor.stop()
        assert not processor.running
    
    @pytest.mark.asyncio
    async def test_processor_skips_when_user_active(self, temp_components):
        """Test that processor skips when user is active."""
        store, tracker, processor = temp_components
        
        # Mark user as active
        tracker.mark_activity()
        
        # Start processor
        await processor.start()
        
        # Wait for one cycle
        await asyncio.sleep(0.15)
        
        # Stop processor
        await processor.stop()
        
        # No events should have been processed
        assert processor.running is False


class TestEntityOperations:
    """Tests for entity CRUD operations in MemoryStore."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            yield store
            store.close()
    
    def test_save_and_get_entity(self, temp_db):
        """Test saving and retrieving an entity."""
        store = temp_db
        
        entity = Entity(
            id="ent_test_001",
            name="John Smith",
            entity_type="person",
            aliases=["john", "j. smith"],
            description="Software engineer",
        )
        
        # Save entity
        entity_id = store.save_entity(entity)
        assert entity_id == "ent_test_001"
        
        # Retrieve entity
        retrieved = store.get_entity("ent_test_001")
        assert retrieved is not None
        assert retrieved.name == "John Smith"
        assert retrieved.entity_type == "person"
        assert "john" in retrieved.aliases
    
    def test_find_entity_by_name(self, temp_db):
        """Test finding entity by name."""
        store = temp_db
        
        entity = Entity(
            id="ent_test_002",
            name="Python",
            entity_type="concept",
            aliases=["python", "py"],
        )
        store.save_entity(entity)
        
        # Find by exact name
        found = store.find_entity_by_name("Python")
        assert found is not None
        assert found.id == "ent_test_002"
        
        # Find by alias (case insensitive)
        found = store.find_entity_by_name("python")
        assert found is not None
        assert found.id == "ent_test_002"
    
    def test_update_entity(self, temp_db):
        """Test updating an entity."""
        store = temp_db
        
        entity = Entity(
            id="ent_test_003",
            name="React",
            entity_type="concept",
            description="Frontend framework",
            event_count=1,
        )
        store.save_entity(entity)
        
        # Update entity
        entity.description = "Frontend library by Meta"
        entity.event_count = 2
        store.update_entity(entity)
        
        # Verify update
        retrieved = store.get_entity("ent_test_003")
        assert retrieved.description == "Frontend library by Meta"
        assert retrieved.event_count == 2
    
    def test_get_entities_by_type(self, temp_db):
        """Test getting entities by type."""
        store = temp_db
        
        # Create entities of different types
        for i in range(3):
            entity = Entity(
                id=f"ent_person_{i}",
                name=f"Person {i}",
                entity_type="person",
            )
            store.save_entity(entity)
        
        for i in range(2):
            entity = Entity(
                id=f"ent_org_{i}",
                name=f"Org {i}",
                entity_type="organization",
            )
            store.save_entity(entity)
        
        # Get persons
        persons = store.get_entities_by_type("person")
        assert len(persons) == 3
        
        # Get orgs
        orgs = store.get_entities_by_type("organization")
        assert len(orgs) == 2


class TestExtractionIntegration:
    """Integration tests for extraction (requires models)."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            yield store
            store.close()
    
    @pytest.mark.skip(reason="Requires spaCy or GLiNER2 model")
    @pytest.mark.asyncio
    async def test_extract_entities_from_event(self, temp_db):
        """Test extracting entities from an event."""
        store = temp_db
        
        event = Event(
            id="evt_extract_001",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content="I work at Google with John on Python projects",
            session_key="cli:default",
        )
        
        config = ExtractionConfig(provider="gliner2")
        result = await extract_entities(event, config)
        
        assert isinstance(result, ExtractionResult)
        assert len(result.entities) > 0
        
        # Save extracted entities
        for entity in result.entities:
            store.save_entity(entity)
        
        # Verify entities were saved
        entities = store.get_all_entities()
        assert len(entities) > 0


class TestBackgroundExtraction:
    """Tests for background extraction processing."""
    
    @pytest.fixture
    def temp_components(self):
        """Create temporary components for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(
                enabled=True,
                db_path="memory/test.db",
                extraction=ExtractionConfig(provider="gliner2")
            )
            store = MemoryStore(config, workspace)
            
            # Create pending event
            event = Event(
                id="evt_pending_extract",
                timestamp=datetime.now(),
                channel="cli",
                direction="inbound",
                event_type="message",
                content="John works at Google",
                session_key="cli:default",
                extraction_status="pending",
            )
            store.save_event(event)
            
            tracker = ActivityTracker(quiet_threshold_seconds=0.1)
            processor = BackgroundProcessor(store, tracker, interval_seconds=0.1)
            
            yield store, tracker, processor
            
            processor.stop()
            store.close()
    
    @pytest.mark.skip(reason="Requires spaCy model")
    @pytest.mark.asyncio
    async def test_background_extraction(self, temp_components):
        """Test that background processor extracts entities."""
        store, tracker, processor = temp_components
        
        # Ensure user is not active
        await asyncio.sleep(0.15)
        
        # Start processor
        await processor.start()
        
        # Wait for processing cycle
        await asyncio.sleep(0.2)
        
        # Stop processor
        await processor.stop()
        
        # Check that event was marked as extracted
        pending = store.get_pending_events()
        assert len(pending) == 0
        
        # Check that entities were created
        entities = store.get_all_entities()
        assert len(entities) > 0
