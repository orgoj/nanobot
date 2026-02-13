"""Tests for MemoryStore operations."""

import json
import pytest
import sqlite3
import struct
import tempfile
from datetime import datetime
from pathlib import Path

from nanobot.config.schema import MemoryConfig
from nanobot.memory.models import Event, Entity, Edge, Fact
from nanobot.memory.store import MemoryStore


class TestMemoryStore:
    """Tests for MemoryStore database operations."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            yield store
            store.close()
    
    def test_store_initialization(self, temp_db):
        """Test that MemoryStore initializes correctly with WAL mode."""
        store = temp_db
        
        # Trigger database initialization (lazy connection)
        store._get_connection()
        
        # Check database file was created
        assert store.db_path.exists()
        
        # Check tables were created
        conn = sqlite3.connect(str(store.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        assert "events" in tables
        assert "entities" in tables
        assert "edges" in tables
        assert "facts" in tables
        assert "topics" in tables
        assert "summary_nodes" in tables
        assert "learnings" in tables
        
        # Check WAL mode is enabled
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode == "wal"
        
        conn.close()
    
    def test_save_and_get_event(self, temp_db):
        """Test saving and retrieving an event."""
        store = temp_db
        
        event = Event(
            id="evt_test_001",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content="Hello, world!",
            session_key="cli:default",
        )
        
        # Save event
        event_id = store.save_event(event)
        assert event_id == "evt_test_001"
        
        # Retrieve event
        retrieved = store.get_event("evt_test_001")
        assert retrieved is not None
        assert retrieved.id == "evt_test_001"
        assert retrieved.content == "Hello, world!"
        assert retrieved.channel == "cli"
        assert retrieved.direction == "inbound"
    
    def test_event_with_embedding(self, temp_db):
        """Test saving event with embedding vector."""
        store = temp_db
        
        # Create a dummy embedding (384 floats for bge-small)
        embedding = [0.1] * 384
        
        event = Event(
            id="evt_test_002",
            timestamp=datetime.now(),
            channel="telegram",
            direction="outbound",
            event_type="message",
            content="Test message",
            session_key="telegram:123",
            content_embedding=embedding,
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_test_002")
        
        assert retrieved is not None
        assert retrieved.content_embedding is not None
        assert len(retrieved.content_embedding) == 384
        assert abs(retrieved.content_embedding[0] - 0.1) < 0.001  # Float comparison
    
    def test_get_events_by_session(self, temp_db):
        """Test retrieving events by session key."""
        store = temp_db
        
        # Create multiple events for same session
        for i in range(5):
            event = Event(
                id=f"evt_session_{i}",
                timestamp=datetime.now(),
                channel="cli",
                direction="inbound",
                event_type="message",
                content=f"Message {i}",
                session_key="cli:test_session",
            )
            store.save_event(event)
        
        # Create event for different session
        other_event = Event(
            id="evt_other",
            timestamp=datetime.now(),
            channel="discord",
            direction="inbound",
            event_type="message",
            content="Other session",
            session_key="discord:other",
        )
        store.save_event(other_event)
        
        # Retrieve events for test session
        events = store.get_events_by_session("cli:test_session", limit=10)
        assert len(events) == 5
        
        # Check they're in reverse chronological order (newest first)
        assert events[0].id == "evt_session_4"  # Last saved
        assert events[4].id == "evt_session_0"  # First saved
    
    def test_get_pending_events(self, temp_db):
        """Test retrieving events pending extraction."""
        store = temp_db
        
        # Create pending events
        for i in range(3):
            event = Event(
                id=f"evt_pending_{i}",
                timestamp=datetime.now(),
                channel="cli",
                direction="inbound",
                event_type="message",
                content=f"Pending {i}",
                session_key="cli:default",
                extraction_status="pending",
            )
            store.save_event(event)
        
        # Create completed event
        completed_event = Event(
            id="evt_completed",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content="Completed",
            session_key="cli:default",
            extraction_status="complete",
        )
        store.save_event(completed_event)
        
        # Get pending events
        pending = store.get_pending_events(limit=10)
        assert len(pending) == 3
        
        # Mark one as complete
        store.mark_event_extracted("evt_pending_0", "complete")
        
        # Check again
        pending = store.get_pending_events(limit=10)
        assert len(pending) == 2
    
    def test_event_not_found(self, temp_db):
        """Test retrieving non-existent event."""
        store = temp_db
        
        retrieved = store.get_event("non_existent_id")
        assert retrieved is None
    
    def test_get_stats(self, temp_db):
        """Test database statistics."""
        store = temp_db
        
        # Create some events
        for i in range(5):
            event = Event(
                id=f"evt_stats_{i}",
                timestamp=datetime.now(),
                channel="cli",
                direction="inbound",
                event_type="message",
                content=f"Stats test {i}",
                session_key="cli:default",
            )
            store.save_event(event)
        
        stats = store.get_stats()
        
        assert stats["events"] == 5
        assert stats["pending_extractions"] == 5
        assert stats["entities"] == 0
        assert stats["edges"] == 0
    
    def test_context_manager(self):
        """Test using MemoryStore as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            
            with MemoryStore(config, workspace) as store:
                event = Event(
                    id="evt_context",
                    timestamp=datetime.now(),
                    channel="cli",
                    direction="inbound",
                    event_type="message",
                    content="Context manager test",
                    session_key="cli:default",
                )
                store.save_event(event)
                
                retrieved = store.get_event("evt_context")
                assert retrieved is not None
            
            # After context exit, connection should be closed
            # (would raise error if we tried to use it)


class TestMemoryStoreEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            yield store
            store.close()
    
    def test_empty_content(self, temp_db):
        """Test saving event with empty content."""
        store = temp_db
        
        event = Event(
            id="evt_empty",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content="",
            session_key="cli:default",
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_empty")
        assert retrieved.content == ""
    
    def test_very_long_content(self, temp_db):
        """Test saving event with very long content."""
        store = temp_db
        
        long_content = "A" * 10000  # 10KB of text
        
        event = Event(
            id="evt_long",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content=long_content,
            session_key="cli:default",
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_long")
        assert len(retrieved.content) == 10000
    
    def test_special_characters(self, temp_db):
        """Test saving event with special characters."""
        store = temp_db
        
        special_content = "Hello! @#$%^&*()_+-=[]{}|;':\",./<>?"
        
        event = Event(
            id="evt_special",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content=special_content,
            session_key="cli:default",
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_special")
        assert retrieved.content == special_content
    
    def test_unicode_content(self, temp_db):
        """Test saving event with unicode characters."""
        store = temp_db
        
        unicode_content = "Hello 世界! 🌍 ñoño café"
        
        event = Event(
            id="evt_unicode",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content=unicode_content,
            session_key="cli:default",
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_unicode")
        assert retrieved.content == unicode_content
    
    def test_event_with_metadata(self, temp_db):
        """Test saving event with metadata."""
        store = temp_db
        
        event = Event(
            id="evt_meta",
            timestamp=datetime.now(),
            channel="cli",
            direction="inbound",
            event_type="message",
            content="Metadata test",
            session_key="cli:default",
            metadata={"key1": "value1", "key2": 123},
        )
        
        store.save_event(event)
        retrieved = store.get_event("evt_meta")
        assert retrieved.metadata == {"key1": "value1", "key2": 123}
