"""Tests for embedding functionality."""

import pytest
import struct
import tempfile
from pathlib import Path
from datetime import datetime

from nanobot.config.schema import MemoryConfig, EmbeddingConfig
from nanobot.memory.embeddings import (
    EmbeddingProvider,
    pack_embedding,
    unpack_embedding,
    cosine_similarity,
)
from nanobot.memory.store import MemoryStore
from nanobot.memory.models import Event


class TestEmbeddingUtils:
    """Tests for embedding utility functions."""
    
    def test_pack_unpack_embedding(self):
        """Test packing and unpacking embeddings."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        packed = pack_embedding(embedding)
        assert isinstance(packed, bytes)
        assert len(packed) == len(embedding) * 4  # 4 bytes per float
        
        unpacked = unpack_embedding(packed)
        assert len(unpacked) == len(embedding)
        for i, (original, recovered) in enumerate(zip(embedding, unpacked)):
            assert abs(original - recovered) < 0.0001
    
    def test_pack_empty_embedding(self):
        """Test packing empty embedding."""
        embedding = []
        packed = pack_embedding(embedding)
        assert packed == b''
        
        unpacked = unpack_embedding(packed)
        assert unpacked == []
    
    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        
        similarity = cosine_similarity(a, b)
        assert abs(similarity - 1.0) < 0.0001
    
    def test_cosine_similarity_opposite(self):
        """Test cosine similarity of opposite vectors."""
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        
        similarity = cosine_similarity(a, b)
        assert abs(similarity - (-1.0)) < 0.0001
    
    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors."""
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        
        similarity = cosine_similarity(a, b)
        assert abs(similarity - 0.0) < 0.0001
    
    def test_cosine_similarity_different_lengths(self):
        """Test that different length vectors raise error."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0]
        
        with pytest.raises(ValueError):
            cosine_similarity(a, b)
    
    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        
        similarity = cosine_similarity(a, b)
        assert similarity == 0.0


class TestEmbeddingProvider:
    """Tests for EmbeddingProvider."""
    
    def test_provider_initialization(self):
        """Test provider initialization."""
        config = EmbeddingConfig(provider="local", lazy_load=True)
        provider = EmbeddingProvider(config)
        
        assert provider.config == config
        assert provider._model is None  # Not loaded yet
        assert not provider._model_loaded
    
    def test_empty_text_embedding(self):
        """Test embedding empty text returns zero vector."""
        config = EmbeddingConfig(provider="local")
        provider = EmbeddingProvider(config)
        
        embedding = provider.embed("")
        assert len(embedding) == 384  # bge-small dimensions
        assert all(x == 0.0 for x in embedding)
        
        embedding = provider.embed("   ")
        assert len(embedding) == 384
        assert all(x == 0.0 for x in embedding)
    
    @pytest.mark.skip(reason="Requires FastEmbed model download")
    def test_local_embedding(self):
        """Test local embedding generation (requires model)."""
        config = EmbeddingConfig(provider="local", lazy_load=True)
        provider = EmbeddingProvider(config)
        
        embedding = provider.embed("Hello world")
        
        assert len(embedding) == 384
        assert not all(x == 0.0 for x in embedding)  # Non-zero
    
    def test_api_fallback(self):
        """Test API fallback when local fails."""
        config = EmbeddingConfig(
            provider="local",
            api_fallback=True,
            lazy_load=True
        )
        provider = EmbeddingProvider(config)
        
        # Force local to fail by not loading model
        embedding = provider._embed_local("test")
        
        # Should return zero vector (API not implemented yet)
        assert len(embedding) == 384
    
    def test_batch_embedding(self):
        """Test batch embedding."""
        config = EmbeddingConfig(provider="local")
        provider = EmbeddingProvider(config)
        
        texts = ["Hello", "World", ""]
        embeddings = provider.embed_batch(texts)
        
        assert len(embeddings) == 2  # Empty text filtered out
        assert all(len(e) == 384 for e in embeddings)
    
    def test_is_ready_api_provider(self):
        """Test is_ready for API provider."""
        config = EmbeddingConfig(provider="api")
        provider = EmbeddingProvider(config)
        
        assert provider.is_ready()  # API is always ready


class TestSemanticSearch:
    """Tests for semantic search functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with sample events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = MemoryConfig(enabled=True, db_path="memory/test.db")
            store = MemoryStore(config, workspace)
            
            # Create events with dummy embeddings
            for i in range(5):
                embedding = [0.1 * (i + 1)] * 384
                embedding_bytes = struct.pack('384f', *embedding)
                
                event = Event(
                    id=f"evt_search_{i}",
                    timestamp=datetime.now(),
                    channel="cli",
                    direction="inbound",
                    event_type="message",
                    content=f"Message about topic {i}",
                    session_key="cli:default",
                    content_embedding=list(embedding),
                )
                store.save_event(event)
            
            yield store
            store.close()
    
    def test_search_events(self, temp_db):
        """Test searching events by embedding."""
        store = temp_db
        
        # Query with similar embedding to event 2
        query_embedding = [0.25] * 384  # Close to event 2 ([0.3] * 384)
        
        results = store.search_events(
            query_embedding=query_embedding,
            limit=3,
            threshold=0.5
        )
        
        assert len(results) > 0
        assert len(results) <= 3
        
        # Check that results are sorted by similarity
        for i in range(len(results) - 1):
            assert results[i][1] >= results[i + 1][1]
    
    def test_search_with_threshold(self, temp_db):
        """Test search with similarity threshold."""
        store = temp_db
        
        query_embedding = [0.5] * 384
        
        # High threshold should return fewer results
        results_high = store.search_events(
            query_embedding=query_embedding,
            threshold=0.9
        )
        
        # Low threshold should return more results
        results_low = store.search_events(
            query_embedding=query_embedding,
            threshold=0.1
        )
        
        assert len(results_low) >= len(results_high)
    
    def test_search_by_session(self, temp_db):
        """Test searching within specific session."""
        store = temp_db
        
        # Add event to different session
        other_event = Event(
            id="evt_other_session",
            timestamp=datetime.now(),
            channel="discord",
            direction="inbound",
            event_type="message",
            content="Different session message",
            session_key="discord:123",
            content_embedding=[0.9] * 384,
        )
        store.save_event(other_event)
        
        query_embedding = [0.9] * 384
        
        # Search in specific session
        results = store.search_events(
            query_embedding=query_embedding,
            session_key="discord:123",
            limit=10
        )
        
        assert len(results) == 1
        assert results[0][0].id == "evt_other_session"
    
    def test_no_results_below_threshold(self, temp_db):
        """Test that no results returned when similarity below threshold."""
        store = temp_db
        
        # Use orthogonal embedding (alternating 1, -1) which is very different from uniform embeddings
        query_embedding = [1.0 if i % 2 == 0 else -1.0 for i in range(384)]
        
        results = store.search_events(
            query_embedding=query_embedding,
            threshold=0.95  # Very high threshold
        )
        
        assert len(results) == 0
