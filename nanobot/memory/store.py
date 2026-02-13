"""SQLite storage layer for the memory system.

This module provides the TurboMemoryStore class which manages all database operations
for the memory system using SQLite with WAL mode for better concurrency.
"""

import json
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from nanobot.config.schema import MemoryConfig
from nanobot.memory.models import Event, Entity, Edge, Fact, Topic, SummaryNode, Learning


class TurboMemoryStore:
    """
    SQLite-based storage for the memory system.
    
    Uses WAL mode (Write-Ahead Logging) for better concurrency:
    - Readers don't block writers
    - Writers don't block readers
    - Better performance for concurrent access
    """
    
    def __init__(self, config: MemoryConfig, workspace: Path):
        """
        Initialize the memory store.
        
        Args:
            config: Memory system configuration
            workspace: Path to workspace directory
        """
        self.config = config
        self.workspace = workspace
        
        # Database file path
        self.db_path = workspace / config.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection (created on first use)
        self._conn: Optional[sqlite3.Connection] = None
        
        # Check if this is a new database and old memory files exist
        is_new_db = not self.db_path.exists()
        
        # Database tables are initialized lazily in _get_connection
        
        # Auto-migrate from legacy format if new database and old files exist
        if is_new_db:
            memory_dir = workspace / "memory"
            legacy_files_exist = (
                (memory_dir / "MEMORY.md").exists() or 
                any(memory_dir.glob("????-??-??.md"))
            )
            if legacy_files_exist:
                logger.info("Legacy memory files detected, starting migration...")
                stats = self.migrate_from_legacy(workspace)
                logger.info(f"Migration complete: {stats}")
        
        logger.info(f"TurboMemoryStore initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection with WAL mode."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            
            # Enable WAL mode for better concurrency
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA cache_size=10000;")
            
            # Initialize tables
            self._init_tables()
            
            logger.debug("Database connection established with WAL mode")
        
        return self._conn
    
    def _init_tables(self):
        """Create all required tables if they don't exist."""
        conn = self._conn
        
        # Events table - immutable record of all interactions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                channel TEXT NOT NULL,
                direction TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                session_key TEXT NOT NULL,
                parent_event_id TEXT,
                person_id TEXT,
                tool_name TEXT,
                extraction_status TEXT DEFAULT 'pending',
                content_embedding BLOB,
                relevance_score REAL DEFAULT 1.0,
                last_accessed REAL,
                metadata TEXT
            )
        """)
        
        # Index on frequently queried columns
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_key);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_extraction ON events(extraction_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_channel ON events(channel);")
        
        # Entities table - people, orgs, concepts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                aliases TEXT,  -- JSON array
                description TEXT,
                name_embedding BLOB,
                description_embedding BLOB,
                source_event_ids TEXT,  -- JSON array
                event_count INTEGER DEFAULT 0,
                first_seen REAL,
                last_seen REAL
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);")
        
        # Edges table - relationships between entities
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                relation_type TEXT,
                strength REAL DEFAULT 0.5,
                source_event_ids TEXT,  -- JSON array
                first_seen REAL,
                last_seen REAL,
                FOREIGN KEY (source_entity_id) REFERENCES entities(id),
                FOREIGN KEY (target_entity_id) REFERENCES entities(id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_entity_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_entity_id);")
        
        # Facts table - subject-predicate-object triplets
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_text TEXT NOT NULL,
                object_entity_id TEXT,
                fact_type TEXT DEFAULT 'attribute',
                confidence REAL DEFAULT 0.8,
                strength REAL DEFAULT 1.0,
                source_event_ids TEXT,  -- JSON array
                valid_from REAL,
                valid_to REAL,
                FOREIGN KEY (subject_entity_id) REFERENCES entities(id),
                FOREIGN KEY (object_entity_id) REFERENCES entities(id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_entity_id);")
        
        # Topics table - theme clusters
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                embedding BLOB,
                event_ids TEXT,  -- JSON array
                first_seen REAL,
                last_seen REAL
            )
        """)
        
        # Summary nodes table - hierarchical summaries
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summary_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                key TEXT NOT NULL UNIQUE,
                parent_id TEXT,
                summary TEXT,
                summary_embedding BLOB,
                events_since_update INTEGER DEFAULT 0,
                last_updated REAL,
                FOREIGN KEY (parent_id) REFERENCES summary_nodes(id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_summary_type ON summary_nodes(node_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_summary_key ON summary_nodes(key);")
        
        # Learnings table - user preferences and insights
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learnings (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                sentiment TEXT DEFAULT 'neutral',
                confidence REAL DEFAULT 0.8,
                tool_name TEXT,
                recommendation TEXT,
                superseded_by TEXT,
                content_embedding BLOB,
                created_at REAL,
                updated_at REAL,
                relevance_score REAL DEFAULT 1.0,
                times_accessed INTEGER DEFAULT 0,
                last_accessed REAL,
                FOREIGN KEY (superseded_by) REFERENCES learnings(id)
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learnings_source ON learnings(source);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learnings_relevance ON learnings(relevance_score);")
        
        conn.commit()
        logger.debug("Database tables initialized")
    
    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    # =========================================================================
    # Event Operations
    # =========================================================================
    
    def save_event(self, event: Event) -> str:
        """
        Save an event to the database.
        
        Args:
            event: The event to save
            
        Returns:
            The event ID
        """
        conn = self._get_connection()
        
        # Serialize embedding if present
        embedding_bytes = None
        if event.content_embedding:
            # Pack float array into bytes (384 floats for bge-small)
            embedding_bytes = struct.pack(f'{len(event.content_embedding)}f', *event.content_embedding)
        
        conn.execute(
            """
            INSERT INTO events (
                id, timestamp, channel, direction, event_type, content,
                session_key, parent_event_id, person_id, tool_name,
                extraction_status, content_embedding, relevance_score,
                last_accessed, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.timestamp.timestamp() if event.timestamp else None,
                event.channel,
                event.direction,
                event.event_type,
                event.content,
                event.session_key,
                event.parent_event_id,
                event.person_id,
                event.tool_name,
                event.extraction_status,
                embedding_bytes,
                event.relevance_score,
                event.last_accessed.timestamp() if event.last_accessed else None,
                json.dumps(event.metadata) if event.metadata else None
            )
        )
        conn.commit()
        
        logger.debug(f"Event saved: {event.id}")
        return event.id
    
    def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve an event by ID."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_event(row)
    
    def get_events_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[Event]:
        """
        Get events for a specific session.
        
        Args:
            session_key: The session identifier (e.g., "cli:default")
            limit: Maximum number of events to return
            offset: Number of events to skip
            
        Returns:
            List of events, most recent first
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM events 
            WHERE session_key = ? 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
            """,
            (session_key, limit, offset)
        ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_pending_events(self, limit: int = 20) -> list[Event]:
        """
        Get events awaiting extraction processing.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of events with extraction_status = 'pending'
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM events 
            WHERE extraction_status = 'pending'
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def mark_event_extracted(self, event_id: str, status: str = "complete"):
        """
        Update extraction status for an event.
        
        Args:
            event_id: The event ID
            status: New status ('complete', 'failed', 'skipped')
        """
        conn = self._get_connection()
        conn.execute(
            "UPDATE events SET extraction_status = ? WHERE id = ?",
            (status, event_id)
        )
        conn.commit()
        
        logger.debug(f"Event {event_id} marked as {status}")
    
    def _row_to_event(self, row: sqlite3.Row) -> Event:
        """Convert a database row to an Event object."""
        # Deserialize embedding
        embedding = None
        if row['content_embedding']:
            floats = struct.unpack('384f', row['content_embedding'])  # bge-small = 384 dims
            embedding = list(floats)
        
        # Deserialize metadata
        metadata = {}
        if row['metadata']:
            metadata = json.loads(row['metadata'])
        
        return Event(
            id=row['id'],
            timestamp=datetime.fromtimestamp(row['timestamp']) if row['timestamp'] else None,
            channel=row['channel'],
            direction=row['direction'],
            event_type=row['event_type'],
            content=row['content'],
            session_key=row['session_key'],
            parent_event_id=row['parent_event_id'],
            person_id=row['person_id'],
            tool_name=row['tool_name'],
            extraction_status=row['extraction_status'],
            content_embedding=embedding,
            relevance_score=row['relevance_score'],
            last_accessed=datetime.fromtimestamp(row['last_accessed']) if row['last_accessed'] else None,
            metadata=metadata
        )
    
    # =========================================================================
    # Semantic Search
    # =========================================================================
    
    def search_events(
        self,
        query_embedding: list[float],
        session_key: str | None = None,
        limit: int = 10,
        threshold: float = 0.5
    ) -> list[tuple[Event, float]]:
        """
        Search events by semantic similarity.
        
        Args:
            query_embedding: The query embedding vector
            session_key: Optional session to restrict search to
            limit: Maximum number of results
            threshold: Minimum similarity score (0-1)
            
        Returns:
            List of (event, similarity_score) tuples, sorted by similarity
        """
        from nanobot.memory.embeddings import cosine_similarity
        
        conn = self._get_connection()
        
        # Get events with embeddings
        if session_key:
            rows = conn.execute(
                """
                SELECT * FROM events 
                WHERE session_key = ? AND content_embedding IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1000
                """,
                (session_key,)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM events 
                WHERE content_embedding IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 1000
                """
            ).fetchall()
        
        # Calculate similarities
        results = []
        for row in rows:
            if row['content_embedding']:
                embedding = struct.unpack(f'{len(query_embedding)}f', row['content_embedding'])
                similarity = cosine_similarity(query_embedding, list(embedding))
                
                if similarity >= threshold:
                    event = self._row_to_event(row)
                    results.append((event, similarity))
        
        # Sort by similarity (highest first) and return top N
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    def search_events_by_text(
        self,
        query: str,
        provider: "EmbeddingProvider",
        session_key: str | None = None,
        limit: int = 10,
        threshold: float = 0.5
    ) -> list[tuple[Event, float]]:
        """
        Search events by text query (automatically embeds query).
        
        Args:
            query: Text query
            provider: Embedding provider to use
            session_key: Optional session to restrict search to
            limit: Maximum number of results
            threshold: Minimum similarity score
            
        Returns:
            List of (event, similarity_score) tuples
        """
        query_embedding = provider.embed(query)
        return self.search_events(query_embedding, session_key, limit, threshold)
    
    def get_similar_entities(
        self,
        name_embedding: list[float],
        entity_type: str | None = None,
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[tuple[Entity, float]]:
        """
        Find entities with similar names.
        
        Args:
            name_embedding: Embedding to compare against
            entity_type: Optional entity type filter
            limit: Maximum number of results
            threshold: Minimum similarity score
            
        Returns:
            List of (entity, similarity_score) tuples
        """
        from nanobot.memory.embeddings import cosine_similarity
        
        conn = self._get_connection()
        
        # Get entities with embeddings
        if entity_type:
            rows = conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? AND name_embedding IS NOT NULL",
                (entity_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entities WHERE name_embedding IS NOT NULL"
            ).fetchall()
        
        # Calculate similarities
        results = []
        for row in rows:
            if row['name_embedding']:
                embedding = struct.unpack(f'{len(name_embedding)}f', row['name_embedding'])
                similarity = cosine_similarity(name_embedding, list(embedding))
                
                if similarity >= threshold:
                    entity = self._row_to_entity(row)
                    results.append((entity, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    # =========================================================================
    # Entity Operations
    # =========================================================================
    
    def save_entity(self, entity: Entity) -> str:
        """
        Save an entity to the database.
        
        Args:
            entity: The entity to save
            
        Returns:
            The entity ID
        """
        conn = self._get_connection()
        
        # Serialize embeddings
        name_embedding_bytes = None
        if entity.name_embedding:
            name_embedding_bytes = struct.pack(f'{len(entity.name_embedding)}f', *entity.name_embedding)
        
        desc_embedding_bytes = None
        if entity.description_embedding:
            desc_embedding_bytes = struct.pack(f'{len(entity.description_embedding)}f', *entity.description_embedding)
        
        conn.execute(
            """
            INSERT OR REPLACE INTO entities (
                id, name, entity_type, aliases, description,
                name_embedding, description_embedding,
                source_event_ids, event_count, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity.id,
                entity.name,
                entity.entity_type,
                json.dumps(entity.aliases),
                entity.description,
                name_embedding_bytes,
                desc_embedding_bytes,
                json.dumps(entity.source_event_ids),
                entity.event_count,
                entity.first_seen.timestamp() if entity.first_seen else None,
                entity.last_seen.timestamp() if entity.last_seen else None,
            )
        )
        conn.commit()
        
        logger.debug(f"Entity saved: {entity.id}")
        return entity.id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Retrieve an entity by ID."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM entities WHERE id = ?",
            (entity_id,)
        ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_entity(row)
    
    def find_entity_by_name(self, name: str) -> Optional[Entity]:
        """
        Find an entity by name (case-insensitive).
        
        Args:
            name: Name to search for
            
        Returns:
            Entity if found, None otherwise
        """
        conn = self._get_connection()
        
        # Search by name or aliases
        row = conn.execute(
            """
            SELECT * FROM entities 
            WHERE LOWER(name) = LOWER(?) 
               OR LOWER(aliases) LIKE LOWER(?)
            LIMIT 1
            """,
            (name, f'%"{name}"%')
        ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_entity(row)
    
    def update_entity(self, entity: Entity):
        """
        Update an existing entity.
        
        Args:
            entity: Entity with updated values
        """
        conn = self._get_connection()
        
        # Serialize embeddings
        name_embedding_bytes = None
        if entity.name_embedding:
            name_embedding_bytes = struct.pack(f'{len(entity.name_embedding)}f', *entity.name_embedding)
        
        desc_embedding_bytes = None
        if entity.description_embedding:
            desc_embedding_bytes = struct.pack(f'{len(entity.description_embedding)}f', *entity.description_embedding)
        
        conn.execute(
            """
            UPDATE entities SET
                name = ?,
                entity_type = ?,
                aliases = ?,
                description = ?,
                name_embedding = ?,
                description_embedding = ?,
                source_event_ids = ?,
                event_count = ?,
                last_seen = ?
            WHERE id = ?
            """,
            (
                entity.name,
                entity.entity_type,
                json.dumps(entity.aliases),
                entity.description,
                name_embedding_bytes,
                desc_embedding_bytes,
                json.dumps(entity.source_event_ids),
                entity.event_count,
                entity.last_seen.timestamp() if entity.last_seen else None,
                entity.id,
            )
        )
        conn.commit()
        
        logger.debug(f"Entity updated: {entity.id}")
    
    def get_entities_by_type(
        self,
        entity_type: str,
        limit: int = 100
    ) -> list[Entity]:
        """
        Get entities of a specific type.
        
        Args:
            entity_type: Type of entities to retrieve
            limit: Maximum number of results
            
        Returns:
            List of entities
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM entities 
            WHERE entity_type = ? 
            ORDER BY event_count DESC
            LIMIT ?
            """,
            (entity_type, limit)
        ).fetchall()
        
        return [self._row_to_entity(row) for row in rows]
    
    def get_all_entities(self, limit: int = 1000) -> list[Entity]:
        """
        Get all entities.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of entities
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM entities 
            ORDER BY event_count DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        
        return [self._row_to_entity(row) for row in rows]
    
    def delete_entity(self, entity_id: str) -> bool:
        """
        Delete an entity from the database.
        
        Args:
            entity_id: ID of entity to delete
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        
        cursor = conn.execute(
            "DELETE FROM entities WHERE id = ?",
            (entity_id,)
        )
        conn.commit()
        
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Entity deleted: {entity_id}")
        
        return deleted
    
    # =========================================================================
    # Edge Operations (for Knowledge Graph)
    # =========================================================================
    
    def create_edge(self, edge: Edge) -> str:
        """
        Create a new edge in the database.
        
        Args:
            edge: Edge to create
            
        Returns:
            Edge ID
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            INSERT INTO edges (
                id, source_entity_id, target_entity_id, relation_type,
                strength, confidence, evidence_count, metadata,
                first_seen, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge.id,
                edge.source_entity_id,
                edge.target_entity_id,
                edge.relation_type,
                edge.strength,
                edge.confidence,
                edge.evidence_count,
                json.dumps(edge.metadata) if edge.metadata else None,
                edge.first_seen.timestamp() if edge.first_seen else None,
                edge.last_updated.timestamp() if edge.last_updated else None,
            )
        )
        conn.commit()
        
        logger.debug(f"Edge created: {edge.id}")
        return edge.id
    
    def get_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str
    ) -> Optional[Edge]:
        """
        Get a specific edge between two entities.
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relation_type: Type of relationship
            
        Returns:
            Edge if found, None otherwise
        """
        conn = self._get_connection()
        
        row = conn.execute(
            """
            SELECT * FROM edges
            WHERE source_entity_id = ? AND target_entity_id = ? AND relation_type = ?
            """,
            (source_id, target_id, relation_type)
        ).fetchone()
        
        if row:
            return self._row_to_edge(row)
        return None
    
    def get_edges_for_entity(
        self,
        entity_id: str,
        min_strength: float = 0.0
    ) -> list[Edge]:
        """
        Get all edges connected to an entity.
        
        Args:
            entity_id: Entity ID
            min_strength: Minimum edge strength to include
            
        Returns:
            List of edges
        """
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM edges
            WHERE (source_entity_id = ? OR target_entity_id = ?)
            AND strength >= ?
            ORDER BY strength DESC
            """,
            (entity_id, entity_id, min_strength)
        ).fetchall()
        
        return [self._row_to_edge(row) for row in rows]
    
    def update_edge(self, edge: Edge):
        """
        Update an existing edge.
        
        Args:
            edge: Edge with updated values
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            UPDATE edges SET
                strength = ?,
                confidence = ?,
                evidence_count = ?,
                metadata = ?,
                last_updated = ?
            WHERE id = ?
            """,
            (
                edge.strength,
                edge.confidence,
                edge.evidence_count,
                json.dumps(edge.metadata) if edge.metadata else None,
                edge.last_updated.timestamp() if edge.last_updated else None,
                edge.id,
            )
        )
        conn.commit()
        
        logger.debug(f"Edge updated: {edge.id}")
    
    def _row_to_edge(self, row: sqlite3.Row) -> Edge:
        """Convert a database row to an Edge object."""
        metadata = {}
        if row['metadata']:
            metadata = json.loads(row['metadata'])
        
        return Edge(
            id=row['id'],
            source_entity_id=row['source_entity_id'],
            target_entity_id=row['target_entity_id'],
            relation_type=row['relation_type'],
            strength=row['strength'],
            confidence=row['confidence'],
            evidence_count=row['evidence_count'],
            metadata=metadata,
            first_seen=datetime.fromtimestamp(row['first_seen']) if row['first_seen'] else None,
            last_updated=datetime.fromtimestamp(row['last_updated']) if row['last_updated'] else None,
        )
    
    # =========================================================================
    # Fact Operations (for Knowledge Graph)
    # =========================================================================
    
    def create_fact(self, fact: Fact) -> str:
        """
        Create a new fact in the database.
        
        Args:
            fact: Fact to create
            
        Returns:
            Fact ID
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            INSERT INTO facts (
                id, subject_id, predicate, object_value,
                confidence, source_event_ids, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.id,
                fact.subject_id,
                fact.predicate,
                fact.object_value,
                fact.confidence,
                json.dumps(fact.source_event_ids),
                fact.first_seen.timestamp() if fact.first_seen else None,
                fact.last_seen.timestamp() if fact.last_seen else None,
            )
        )
        conn.commit()
        
        logger.debug(f"Fact created: {fact.id}")
        return fact.id
    
    def get_facts_for_entity(self, entity_id: str) -> list[Fact]:
        """
        Get all facts about an entity (as subject or object).
        
        Args:
            entity_id: Entity ID
            
        Returns:
            List of facts
        """
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM facts
            WHERE subject_id = ? OR object_id = ?
            ORDER BY confidence DESC
            """,
            (entity_id, entity_id)
        ).fetchall()
        
        return [self._row_to_fact(row) for row in rows]
    
    def get_facts_for_subject(self, subject_id: str) -> list[Fact]:
        """
        Get all facts where entity is the subject.
        
        Args:
            subject_id: Subject entity ID
            
        Returns:
            List of facts
        """
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM facts
            WHERE subject_id = ?
            ORDER BY confidence DESC
            """,
            (subject_id,)
        ).fetchall()
        
        return [self._row_to_fact(row) for row in rows]
    
    def update_fact(self, fact: Fact):
        """
        Update an existing fact.
        
        Args:
            fact: Fact with updated values
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            UPDATE facts SET
                object_value = ?,
                confidence = ?,
                evidence_count = ?,
                last_seen = ?
            WHERE id = ?
            """,
            (
                fact.object_value,
                fact.confidence,
                fact.evidence_count,
                fact.last_seen.timestamp() if fact.last_seen else None,
                fact.id,
            )
        )
        conn.commit()
        
        logger.debug(f"Fact updated: {fact.id}")
    
    def _row_to_fact(self, row: sqlite3.Row) -> Fact:
        """Convert a database row to a Fact object."""
        source_ids = []
        if row['source_event_ids']:
            source_ids = json.loads(row['source_event_ids'])
        
        return Fact(
            id=row['id'],
            subject_id=row['subject_id'],
            predicate=row['predicate'],
            object_value=row['object_value'],
            confidence=row['confidence'],
            source_event_ids=source_ids,
            first_seen=datetime.fromtimestamp(row['first_seen']) if row['first_seen'] else None,
            last_seen=datetime.fromtimestamp(row['last_seen']) if row['last_seen'] else None,
        )
    
    def search_similar_entities(
        self,
        embedding: list[float],
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[Entity]:
        """
        Search for entities with similar embeddings.
        
        Args:
            embedding: Query embedding vector
            limit: Maximum results
            threshold: Minimum similarity (0-1)
            
        Returns:
            List of similar entities
        """
        # Get all entities with embeddings
        entities = self.get_entities_by_type("person", limit=1000)  # Get all types
        
        # Calculate cosine similarity for each
        from nanobot.memory.embeddings import cosine_similarity
        
        similarities = []
        for entity in entities:
            if entity.name_embedding:
                sim = cosine_similarity(embedding, entity.name_embedding)
                if sim >= threshold:
                    similarities.append((entity, sim))
        
        # Sort by similarity and return top results
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in similarities[:limit]]
    
    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert a database row to an Entity object."""
        # Deserialize name embedding
        name_embedding = None
        if row['name_embedding']:
            floats = struct.unpack('384f', row['name_embedding'])
            name_embedding = list(floats)
        
        # Deserialize description embedding
        desc_embedding = None
        if row['description_embedding']:
            floats = struct.unpack('384f', row['description_embedding'])
            desc_embedding = list(floats)
        
        # Deserialize aliases and source event IDs
        aliases = []
        if row['aliases']:
            aliases = json.loads(row['aliases'])
        
        source_ids = []
        if row['source_event_ids']:
            source_ids = json.loads(row['source_event_ids'])
        
        return Entity(
            id=row['id'],
            name=row['name'],
            entity_type=row['entity_type'],
            aliases=aliases,
            description=row['description'] or "",
            name_embedding=name_embedding,
            description_embedding=desc_embedding,
            source_event_ids=source_ids,
            event_count=row['event_count'] or 0,
            first_seen=datetime.fromtimestamp(row['first_seen']) if row['first_seen'] else None,
            last_seen=datetime.fromtimestamp(row['last_seen']) if row['last_seen'] else None
        )
    
    # =========================================================================
    # Statistics and Maintenance
    # =========================================================================
    
    def get_stats(self) -> dict:
        """
        Get database statistics.
        
        Returns:
            Dictionary with table row counts and other stats
        """
        conn = self._get_connection()
        
        tables = ['events', 'entities', 'edges', 'facts', 'topics', 'summary_nodes', 'learnings']
        stats = {}
        
        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count
        
        # Pending extractions
        pending = conn.execute(
            "SELECT COUNT(*) FROM events WHERE extraction_status = 'pending'"
        ).fetchone()[0]
        stats['pending_extractions'] = pending
        
        return stats
    
    # =========================================================================
    # Summary Node Operations (for Hierarchical Summaries - Phase 4)
    # =========================================================================
    
    def create_summary_node(self, node: SummaryNode) -> str:
        """
        Create a new summary node in the database.
        
        Args:
            node: SummaryNode to create
            
        Returns:
            Node ID
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            INSERT INTO summary_nodes (
                id, node_type, key, parent_id, summary, summary_embedding,
                events_since_update, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.node_type,
                node.key,
                node.parent_id,
                node.summary,
                None,  # summary_embedding (not implemented yet)
                node.events_since_update,
                node.last_updated.timestamp() if node.last_updated else None,
            )
        )
        conn.commit()
        
        logger.debug(f"Summary node created: {node.id}")
        return node.id
    
    def get_summary_node(self, node_id: str) -> Optional[SummaryNode]:
        """
        Get a summary node by ID.
        
        Args:
            node_id: Node ID
            
        Returns:
            SummaryNode if found, None otherwise
        """
        conn = self._get_connection()
        
        row = conn.execute(
            "SELECT * FROM summary_nodes WHERE id = ?",
            (node_id,)
        ).fetchone()
        
        if row:
            return self._row_to_summary_node(row)
        return None
    
    def get_all_summary_nodes(self) -> list[SummaryNode]:
        """
        Get all summary nodes.
        
        Returns:
            List of all summary nodes
        """
        conn = self._get_connection()
        
        rows = conn.execute("SELECT * FROM summary_nodes").fetchall()
        return [self._row_to_summary_node(row) for row in rows]
    
    def update_summary_node(self, node: SummaryNode):
        """
        Update an existing summary node.
        
        Args:
            node: SummaryNode with updated values
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            UPDATE summary_nodes SET
                summary = ?,
                events_since_update = ?,
                last_updated = ?
            WHERE id = ?
            """,
            (
                node.summary,
                node.events_since_update,
                node.last_updated.timestamp() if node.last_updated else None,
                node.id,
            )
        )
        conn.commit()
        
        logger.debug(f"Summary node updated: {node.id}")
    
    def _row_to_summary_node(self, row: sqlite3.Row) -> SummaryNode:
        """Convert a database row to a SummaryNode object."""
        return SummaryNode(
            id=row['id'],
            node_type=row['node_type'],
            key=row['key'],
            parent_id=row['parent_id'],
            summary=row['summary'] or "",
            summary_embedding=row['summary_embedding'],
            events_since_update=row['events_since_update'] or 0,
            last_updated=datetime.fromtimestamp(row['last_updated']) if row['last_updated'] else None,
        )
    
    def get_events_for_channel(self, channel: str, limit: int = 50) -> list[Event]:
        """Get events for a specific channel."""
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM events 
            WHERE channel = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (channel, limit)
        ).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_entities_for_channel(self, channel: str, limit: int = 20) -> list[Entity]:
        """Get entities mentioned in a specific channel."""
        conn = self._get_connection()
        
        # Get entities that have events from this channel
        rows = conn.execute(
            """
            SELECT DISTINCT e.* FROM entities e
            JOIN events ev ON ev.content LIKE '%' || e.name || '%'
            WHERE ev.channel = ?
            ORDER BY e.event_count DESC
            LIMIT ?
            """,
            (channel, limit)
        ).fetchall()
        
        return [self._row_to_entity(row) for row in rows]
    
    def vacuum(self):
        """Optimize database (reclaim space, defragment)."""
        conn = self._get_connection()
        conn.execute("VACUUM;")
        conn.commit()
        logger.info("Database vacuumed")
    
    # =========================================================================
    # Learning Operations (Phase 6: Learning + User Preferences)
    # =========================================================================
    
    def create_learning(self, learning: Learning) -> str:
        """
        Create a new learning in the database.
        
        Args:
            learning: Learning to create
            
        Returns:
            Learning ID
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            INSERT INTO learnings (
                id, content, source, sentiment, confidence, tool_name,
                recommendation, superseded_by, content_embedding,
                created_at, updated_at, relevance_score, times_accessed, last_accessed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                learning.id,
                learning.content,
                learning.source,
                learning.sentiment,
                learning.confidence,
                learning.tool_name,
                learning.recommendation,
                learning.superseded_by,
                learning.content_embedding,
                learning.created_at.timestamp() if learning.created_at else None,
                learning.updated_at.timestamp() if learning.updated_at else None,
                learning.relevance_score,
                learning.times_accessed,
                learning.last_accessed.timestamp() if learning.last_accessed else None,
            )
        )
        conn.commit()
        
        logger.debug(f"Learning created: {learning.id}")
        return learning.id
    
    def get_learning(self, learning_id: str) -> Optional[Learning]:
        """
        Get a learning by ID.
        
        Args:
            learning_id: Learning ID
            
        Returns:
            Learning if found, None otherwise
        """
        conn = self._get_connection()
        
        row = conn.execute(
            "SELECT * FROM learnings WHERE id = ?",
            (learning_id,)
        ).fetchone()
        
        if row:
            return self._row_to_learning(row)
        return None
    
    def get_all_learnings(self, active_only: bool = True) -> list[Learning]:
        """
        Get all learnings, optionally filtering out superseded ones.
        
        Args:
            active_only: If True, only return non-superseded learnings
            
        Returns:
            List of learnings
        """
        conn = self._get_connection()
        
        if active_only:
            rows = conn.execute(
                "SELECT * FROM learnings WHERE superseded_by IS NULL ORDER BY relevance_score DESC"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM learnings ORDER BY created_at DESC").fetchall()
        
        return [self._row_to_learning(row) for row in rows]
    
    def update_learning(self, learning: Learning):
        """
        Update an existing learning.
        
        Args:
            learning: Learning with updated values
        """
        conn = self._get_connection()
        
        conn.execute(
            """
            UPDATE learnings SET
                content = ?,
                sentiment = ?,
                confidence = ?,
                recommendation = ?,
                superseded_by = ?,
                relevance_score = ?,
                times_accessed = ?,
                last_accessed = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                learning.content,
                learning.sentiment,
                learning.confidence,
                learning.recommendation,
                learning.superseded_by,
                learning.relevance_score,
                learning.times_accessed,
                learning.last_accessed.timestamp() if learning.last_accessed else None,
                datetime.now().timestamp(),
                learning.id,
            )
        )
        conn.commit()
        
        logger.debug(f"Learning updated: {learning.id}")
    
    def delete_learning(self, learning_id: str) -> bool:
        """
        Delete a learning from the database.
        
        Args:
            learning_id: ID of learning to delete
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        
        cursor = conn.execute(
            "DELETE FROM learnings WHERE id = ?",
            (learning_id,)
        )
        conn.commit()
        
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Learning deleted: {learning_id}")
        
        return deleted
    
    def get_learnings_by_source(self, source: str, limit: int = 100) -> list[Learning]:
        """
        Get learnings by source type.
        
        Args:
            source: Source type (e.g., "user_feedback", "self_evaluation")
            limit: Maximum results
            
        Returns:
            List of learnings
        """
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM learnings 
            WHERE source = ? AND superseded_by IS NULL
            ORDER BY relevance_score DESC, created_at DESC
            LIMIT ?
            """,
            (source, limit)
        ).fetchall()
        
        return [self._row_to_learning(row) for row in rows]
    
    def get_high_relevance_learnings(self, min_score: float = 0.7, limit: int = 50) -> list[Learning]:
        """
        Get learnings with high relevance scores.
        
        Args:
            min_score: Minimum relevance score
            limit: Maximum results
            
        Returns:
            List of high-relevance learnings
        """
        conn = self._get_connection()
        
        rows = conn.execute(
            """
            SELECT * FROM learnings 
            WHERE relevance_score >= ? AND superseded_by IS NULL
            ORDER BY relevance_score DESC
            LIMIT ?
            """,
            (min_score, limit)
        ).fetchall()
        
        return [self._row_to_learning(row) for row in rows]
    
    def _row_to_learning(self, row: sqlite3.Row) -> Learning:
        """Convert a database row to a Learning object."""
        return Learning(
            id=row['id'],
            content=row['content'],
            source=row['source'],
            sentiment=row['sentiment'],
            confidence=row['confidence'],
            tool_name=row['tool_name'],
            recommendation=row['recommendation'],
            superseded_by=row['superseded_by'],
            content_embedding=row['content_embedding'],
            created_at=datetime.fromtimestamp(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromtimestamp(row['updated_at']) if row['updated_at'] else None,
            relevance_score=row['relevance_score'] or 1.0,
            times_accessed=row['times_accessed'] or 0,
            last_accessed=datetime.fromtimestamp(row['last_accessed']) if row['last_accessed'] else None,
        )
    
    def migrate_from_legacy(self, workspace: Path) -> dict:
        """
        Migrate data from old file-based memory system (MEMORY.md + daily notes).
        
        Reads the legacy MEMORY.md and YYYY-MM-DD.md files and imports them
        as events into the SQLite database.
        
        Args:
            workspace: Path to workspace directory containing memory/ folder
            
        Returns:
            Migration statistics {"events_imported": int, "files_processed": int}
        """
        from pathlib import Path
        
        memory_dir = workspace / "memory"
        if not memory_dir.exists():
            return {"events_imported": 0, "files_processed": 0}
        
        stats = {"events_imported": 0, "files_processed": 0}
        
        # Import MEMORY.md as a long-term memory event
        memory_file = memory_dir / "MEMORY.md"
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8")
            if content.strip():
                event = Event(
                    content=f"Legacy long-term memory:\n\n{content[:1000]}",  # Truncate if too long
                    event_type="legacy_import",
                    source="memory.md_migration",
                    importance=0.8
                )
                self.save_event(event)
                stats["events_imported"] += 1
                stats["files_processed"] += 1
                logger.info(f"Migrated MEMORY.md ({len(content)} chars)")
        
        # Import daily notes as events
        for file_path in memory_dir.glob("????-??-??.md"):
            try:
                # Extract date from filename
                date_str = file_path.stem  # YYYY-MM-DD
                content = file_path.read_text(encoding="utf-8")
                
                if content.strip():
                    event = Event(
                        content=f"Legacy daily notes ({date_str}):\n\n{content[:2000]}",  # Truncate if too long
                        event_type="legacy_import",
                        source="daily_notes_migration",
                        timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
                        importance=0.6
                    )
                    self.save_event(event)
                    stats["events_imported"] += 1
                    stats["files_processed"] += 1
                    logger.info(f"Migrated daily notes: {date_str} ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to migrate {file_path}: {e}")
        
        logger.info(f"Migration complete: {stats['events_imported']} events from {stats['files_processed']} files")
        return stats
    
    def get_memory_context(self, limit: int = 50) -> str:
        """
        Get memory context formatted for system prompt injection.
        
        Retrieves recent events, important entities, active learnings,
        and summary nodes to provide context for the LLM.
        
        Args:
            limit: Maximum number of recent events to include
            
        Returns:
            Formatted memory context string
        """
        parts = []
        
        # Get recent events
        recent_events = self.get_recent_events(limit=limit)
        if recent_events:
            parts.append("## Recent Activity")
            for event in recent_events:
                parts.append(f"- [{event.timestamp.strftime('%Y-%m-%d %H:%M')}] {event.event_type}: {event.content[:100]}")
        
        # Get important entities
        entities = self.get_all_entities()
        important_entities = [e for e in entities if e.event_count > 2][:10]
        if important_entities:
            parts.append("\n## Key Entities")
            for entity in important_entities:
                parts.append(f"- {entity.name} ({entity.entity_type}): {entity.description or 'No description'}")
        
        # Get active learnings
        learnings = self.get_active_learnings(limit=5)
        if learnings:
            parts.append("\n## Learned Preferences")
            for learning in learnings:
                parts.append(f"- {learning.content}")
        
        # Get latest summary
        summaries = self.get_summary_nodes(parent_id=None)
        if summaries:
            latest = max(summaries, key=lambda s: s.created_at or datetime.min)
            parts.append(f"\n## Conversation Summary\n{latest.content}")
        
        return "\n".join(parts) if parts else ""
    """
    DEPRECATED: Use TurboMemoryStore instead.
    
    This class exists only for backward compatibility.
    It will be removed in a future version.
    """
    
    def __init__(self, *args, **kwargs):
        import warnings
        warnings.warn(
            "MemoryStore is deprecated. Use TurboMemoryStore instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)
    
    def migrate_from_legacy(self, workspace: Path) -> dict:
        """
        Migrate data from old file-based memory system (MEMORY.md + daily notes).
        
        Reads the legacy MEMORY.md and YYYY-MM-DD.md files and imports them
        as events into the SQLite database.
        
        Args:
            workspace: Path to workspace directory containing memory/ folder
            
        Returns:
            Migration statistics {"events_imported": int, "files_processed": int}
        """
        from pathlib import Path
        
        memory_dir = workspace / "memory"
        if not memory_dir.exists():
            return {"events_imported": 0, "files_processed": 0}
        
        stats = {"events_imported": 0, "files_processed": 0}
        
        # Import MEMORY.md as a long-term memory event
        memory_file = memory_dir / "MEMORY.md"
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8")
            if content.strip():
                event = Event(
                    content=f"Legacy long-term memory:\n\n{content[:1000]}",  # Truncate if too long
                    event_type="legacy_import",
                    source="memory.md_migration",
                    importance=0.8
                )
                self.save_event(event)
                stats["events_imported"] += 1
                stats["files_processed"] += 1
                logger.info(f"Migrated MEMORY.md ({len(content)} chars)")
        
        # Import daily notes as events
        for file_path in memory_dir.glob("????-??-??.md"):
            try:
                # Extract date from filename
                date_str = file_path.stem  # YYYY-MM-DD
                content = file_path.read_text(encoding="utf-8")
                
                if content.strip():
                    event = Event(
                        content=f"Legacy daily notes ({date_str}):\n\n{content[:2000]}",  # Truncate if too long
                        event_type="legacy_import",
                        source="daily_notes_migration",
                        timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
                        importance=0.6
                    )
                    self.save_event(event)
                    stats["events_imported"] += 1
                    stats["files_processed"] += 1
                    logger.info(f"Migrated daily notes: {date_str} ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to migrate {file_path}: {e}")
        
        logger.info(f"Migration complete: {stats['events_imported']} events from {stats['files_processed']} files")
        return stats
    
    def get_memory_context(self, limit: int = 50) -> str:
        """
        Get memory context formatted for system prompt injection.
        
        Retrieves recent events, important entities, active learnings,
        and summary nodes to provide context for the LLM.
        
        Args:
            limit: Maximum number of recent events to include
            
        Returns:
            Formatted memory context string
        """
        parts = []
        
        # Get recent events
        recent_events = self.get_recent_events(limit=limit)
        if recent_events:
            parts.append("## Recent Activity")
            for event in recent_events:
                parts.append(f"- [{event.timestamp.strftime('%Y-%m-%d %H:%M')}] {event.event_type}: {event.content[:100]}")
        
        # Get important entities
        entities = self.get_all_entities()
        important_entities = [e for e in entities if e.event_count > 2][:10]
        if important_entities:
            parts.append("\n## Key Entities")
            for entity in important_entities:
                parts.append(f"- {entity.name} ({entity.entity_type}): {entity.description or 'No description'}")
        
        # Get active learnings
        learnings = self.get_active_learnings(limit=5)
        if learnings:
            parts.append("\n## Learned Preferences")
            for learning in learnings:
                parts.append(f"- {learning.content}")
        
        # Get latest summary
        summaries = self.get_summary_nodes(parent_id=None)
        if summaries:
            latest = max(summaries, key=lambda s: s.created_at or datetime.min)
            parts.append(f"\n## Conversation Summary\n{latest.content}")
        
        return "\n".join(parts) if parts else ""
