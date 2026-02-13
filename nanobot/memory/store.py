"""SQLite storage layer for the memory system.

This module provides the TurboMemoryStore class which manages all database operations
for the memory system using SQLite with WAL mode for better concurrency.
"""

import json
import math
import sqlite3
import struct
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from nanobot.config.schema import TurboMemoryConfig as MemoryConfig
from nanobot.memory.models import Entity, Event, Fact, Learning, SummaryNode


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

        self._init_db()

        # Phase 1.4: Auto-migration from legacy files
        if is_new_db:
            stats = self.migrate_from_legacy(workspace)
            if stats["events_imported"] > 0:
                logger.info(
                    f"Auto-migrated {stats['events_imported']} events from legacy memory files"
                )

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create SQLite connection with WAL mode."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row

            # Enable WAL mode
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")

        return self._conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()

        # Events table - immutable interaction log
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                channel TEXT NOT NULL,
                direction TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                content_embedding BLOB,
                session_key TEXT NOT NULL,
                parent_event_id TEXT,
                person_id TEXT,
                tool_name TEXT,
                extraction_status TEXT DEFAULT 'pending',
                relevance_score REAL DEFAULT 1.0,
                last_accessed DATETIME,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (parent_event_id) REFERENCES events(id)
            )
        """
        )

        # Entities table - people, orgs, concepts
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                description TEXT DEFAULT '',
                name_embedding BLOB,
                description_embedding BLOB,
                source_event_ids TEXT DEFAULT '[]',
                event_count INTEGER DEFAULT 0,
                first_seen DATETIME,
                last_seen DATETIME
            )
        """
        )

        # Edges table - relationships between entities
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                relation_type TEXT DEFAULT 'general',
                strength REAL DEFAULT 0.5,
                source_event_ids TEXT DEFAULT '[]',
                first_seen DATETIME,
                last_seen DATETIME,
                FOREIGN KEY (source_entity_id) REFERENCES entities(id),
                FOREIGN KEY (target_entity_id) REFERENCES entities(id)
            )
        """
        )

        # Facts table - subject-predicate-object triplets
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_text TEXT NOT NULL,
                object_entity_id TEXT,
                fact_type TEXT DEFAULT 'attribute',
                confidence REAL DEFAULT 0.8,
                strength REAL DEFAULT 1.0,
                source_event_ids TEXT DEFAULT '[]',
                valid_from DATETIME,
                valid_to DATETIME,
                FOREIGN KEY (subject_entity_id) REFERENCES entities(id),
                FOREIGN KEY (object_entity_id) REFERENCES entities(id)
            )
        """
        )

        # Summary nodes - hierarchical summaries
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS summary_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                key TEXT NOT NULL UNIQUE,
                parent_id TEXT,
                summary TEXT DEFAULT '',
                summary_embedding BLOB,
                events_since_update INTEGER DEFAULT 0,
                last_updated DATETIME,
                FOREIGN KEY (parent_id) REFERENCES summary_nodes(id)
            )
        """
        )

        # Learnings table - user feedback and self-improvement
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learnings (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                sentiment TEXT DEFAULT 'neutral',
                confidence REAL DEFAULT 0.8,
                tool_name TEXT,
                recommendation TEXT DEFAULT '',
                superseded_by TEXT,
                content_embedding BLOB,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                relevance_score REAL DEFAULT 1.0,
                times_accessed INTEGER DEFAULT 0,
                last_accessed DATETIME,
                FOREIGN KEY (superseded_by) REFERENCES learnings(id)
            )
        """
        )

        # Create indexes for fast lookup
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_extraction ON events(extraction_status)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject_entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_summary_key ON summary_nodes(key)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_learnings_relevance ON learnings(relevance_score)"
        )

        conn.commit()

    # --- CRUD Operations for Events ---

    def save_event(self, event: Event) -> None:
        """Save an event to the database."""
        conn = self._get_connection()

        # Pack embedding if present
        embedding_blob = None
        if event.content_embedding:
            embedding_blob = event.content_embedding

        conn.execute(
            """
            INSERT OR REPLACE INTO events (
                id, timestamp, channel, direction, event_type, content,
                content_embedding, session_key, parent_event_id, person_id,
                tool_name, extraction_status, relevance_score, last_accessed, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.timestamp.isoformat(),
                event.channel,
                event.direction,
                event.event_type,
                event.content,
                embedding_blob,
                event.session_key,
                event.parent_event_id,
                event.person_id,
                event.tool_name,
                event.extraction_status,
                event.relevance_score,
                event.last_accessed.isoformat() if event.last_accessed else None,
                json.dumps(event.metadata),
            ),
        )
        conn.commit()

    def get_event(self, event_id: str) -> Optional[Event]:
        """Retrieve an event by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()

        if row:
            return self._row_to_event(row)
        return None

    def get_recent_events(self, limit: int = 50, session_key: Optional[str] = None) -> list[Event]:
        """Get most recent events."""
        conn = self._get_connection()
        query = "SELECT * FROM events"
        params = []

        if session_key:
            query += " WHERE session_key = ?"
            params.append(session_key)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_pending_events(self, limit: int = 20) -> list[Event]:
        """Get events that haven't been extracted yet."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM events WHERE extraction_status = 'pending' ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def mark_event_extracted(self, event_id: str, status: str = "complete") -> None:
        """Update extraction status of an event."""
        conn = self._get_connection()
        conn.execute("UPDATE events SET extraction_status = ? WHERE id = ?", (status, event_id))
        conn.commit()

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        """Convert database row to Event object."""
        return Event(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            channel=row["channel"],
            direction=row["direction"],
            event_type=row["event_type"],
            content=row["content"],
            session_key=row["session_key"],
            parent_event_id=row["parent_event_id"],
            person_id=row["person_id"],
            tool_name=row["tool_name"],
            extraction_status=row["extraction_status"],
            content_embedding=row["content_embedding"],
            relevance_score=row["relevance_score"],
            last_accessed=datetime.fromisoformat(row["last_accessed"])
            if row["last_accessed"]
            else None,
            metadata=json.loads(row["metadata"]),
        )

    # --- CRUD Operations for Entities ---

    def save_entity(self, entity: Entity) -> None:
        """Save or update an entity."""
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO entities (
                id, name, entity_type, aliases, description,
                name_embedding, description_embedding, source_event_ids,
                event_count, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity.id,
                entity.name,
                entity.entity_type,
                json.dumps(entity.aliases),
                entity.description,
                entity.name_embedding,
                entity.description_embedding,
                json.dumps(entity.source_event_ids),
                entity.event_count,
                entity.first_seen.isoformat() if entity.first_seen else None,
                entity.last_seen.isoformat() if entity.last_seen else None,
            ),
        )
        conn.commit()

    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """Retrieve an entity by its canonical name."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM entities WHERE name = ?", (name,)).fetchone()

        if row:
            return self._row_to_entity(row)
        return None

    def get_all_entities(self, limit: int = 100) -> list[Entity]:
        """Retrieve all entities."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM entities ORDER BY event_count DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert database row to Entity object."""
        return Entity(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            aliases=json.loads(row["aliases"]),
            description=row["description"],
            name_embedding=row["name_embedding"],
            description_embedding=row["description_embedding"],
            source_event_ids=json.loads(row["source_event_ids"]),
            event_count=row["event_count"],
            first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
            last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
        )

    # --- CRUD Operations for Facts ---

    def save_fact(self, fact: Fact) -> None:
        """Save or update a fact."""
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO facts (
                id, subject_entity_id, predicate, object_text, object_entity_id,
                fact_type, confidence, strength, source_event_ids, valid_from, valid_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact.id,
                fact.subject_entity_id,
                fact.predicate,
                fact.object_text,
                fact.object_entity_id,
                fact.fact_type,
                fact.confidence,
                fact.strength,
                json.dumps(fact.source_event_ids),
                fact.valid_from.isoformat() if fact.valid_from else None,
                fact.valid_to.isoformat() if fact.valid_to else None,
            ),
        )
        conn.commit()

    def get_facts_for_entity(self, entity_id: str) -> list[Fact]:
        """Retrieve all facts where entity is the subject."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM facts WHERE subject_entity_id = ?", (entity_id,)
        ).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def _row_to_fact(self, row: sqlite3.Row) -> Fact:
        """Convert database row to Fact object."""
        return Fact(
            id=row["id"],
            subject_entity_id=row["subject_entity_id"],
            predicate=row["predicate"],
            object_text=row["object_text"],
            object_entity_id=row["object_entity_id"],
            fact_type=row["fact_type"],
            confidence=row["confidence"],
            strength=row["strength"],
            source_event_ids=json.loads(row["source_event_ids"]),
            valid_from=datetime.fromisoformat(row["valid_from"]) if row["valid_from"] else None,
            valid_to=datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
        )

    # --- CRUD Operations for SummaryNodes ---

    def save_summary_node(self, node: SummaryNode) -> None:
        """Save or update a summary node."""
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO summary_nodes (
                id, node_type, key, parent_id, summary,
                summary_embedding, events_since_update, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.node_type,
                node.key,
                node.parent_id,
                node.summary,
                node.summary_embedding,
                node.events_since_update,
                node.last_updated.isoformat() if node.last_updated else None,
            ),
        )
        conn.commit()

    def get_summary_node(self, key: str) -> Optional[SummaryNode]:
        """Retrieve a summary node by key."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM summary_nodes WHERE key = ?", (key,)).fetchone()

        if row:
            return self._row_to_summary_node(row)
        return None

    def get_summary_nodes(self, parent_id: Optional[str] = None) -> list[SummaryNode]:
        """Retrieve summary nodes by parent ID."""
        conn = self._get_connection()
        if parent_id:
            rows = conn.execute(
                "SELECT * FROM summary_nodes WHERE parent_id = ?", (parent_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM summary_nodes WHERE parent_id IS NULL").fetchall()

        return [self._row_to_summary_node(row) for row in rows]

    def _row_to_summary_node(self, row: sqlite3.Row) -> SummaryNode:
        """Convert database row to SummaryNode object."""
        return SummaryNode(
            id=row["id"],
            node_type=row["node_type"],
            key=row["key"],
            parent_id=row["parent_id"],
            summary=row["summary"],
            summary_embedding=row["summary_embedding"],
            events_since_update=row["events_since_update"],
            last_updated=datetime.fromisoformat(row["last_updated"])
            if row["last_updated"]
            else None,
        )

    # --- CRUD Operations for Learnings ---

    def save_learning(self, learning: Learning) -> None:
        """Save or update a learning record."""
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO learnings (
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
                learning.created_at.isoformat() if learning.created_at else None,
                learning.updated_at.isoformat() if learning.updated_at else None,
                learning.relevance_score,
                learning.times_accessed,
                learning.last_accessed.isoformat() if learning.last_accessed else None,
            ),
        )
        conn.commit()

    def get_active_learnings(self, limit: int = 20) -> list[Learning]:
        """Get most relevant active learnings."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM learnings
            WHERE superseded_by IS NULL
            ORDER BY relevance_score DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_learning(row) for row in rows]

    def _row_to_learning(self, row: sqlite3.Row) -> Learning:
        """Convert database row to Learning object."""
        return Learning(
            id=row["id"],
            content=row["content"],
            source=row["source"],
            sentiment=row["sentiment"],
            confidence=row["confidence"],
            tool_name=row["tool_name"],
            recommendation=row["recommendation"],
            superseded_by=row["superseded_by"],
            content_embedding=row["content_embedding"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            relevance_score=row["relevance_score"],
            times_accessed=row["times_accessed"],
            last_accessed=datetime.fromisoformat(row["last_accessed"])
            if row["last_accessed"]
            else None,
        )

    # --- Search and Retrieval ---

    def semantic_search_events(
        self,
        query_embedding: bytes,
        session_key: Optional[str] = None,
        limit: int = 10,
        min_relevance: float = 0.5,
    ) -> list[tuple[Event, float]]:
        """
        Search events by semantic similarity.

        This uses brute-force cosine similarity over the SQLite blob columns.
        For small to medium databases (< 100k events), this is very fast.
        """
        conn = self._get_connection()
        query = "SELECT * FROM events WHERE content_embedding IS NOT NULL"
        params = []

        if session_key:
            query += " AND session_key = ?"
            params.append(session_key)

        rows = conn.execute(query, params).fetchall()

        results = []
        query_vector = self._unpack_embedding(query_embedding)

        for row in rows:
            event_vector = self._unpack_embedding(row["content_embedding"])
            similarity = self._cosine_similarity(query_vector, event_vector)

            if similarity >= min_relevance:
                event = self._row_to_event(row)
                results.append((event, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _unpack_embedding(self, blob: bytes) -> list[float]:
        """Unpack binary blob to list of floats."""
        n = len(blob) // 4
        return list(struct.unpack(f"{n}f", blob))

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(a * a for a in v2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    # --- Analytics and Stats ---

    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = self._get_connection()
        stats = {}

        # Basic counts
        stats["events"] = conn.execute("SELECT count(*) FROM events").fetchone()[0]
        stats["entities"] = conn.execute("SELECT count(*) FROM entities").fetchone()[0]
        stats["edges"] = conn.execute("SELECT count(*) FROM edges").fetchone()[0]
        stats["facts"] = conn.execute("SELECT count(*) FROM facts").fetchone()[0]
        stats["summary_nodes"] = conn.execute("SELECT count(*) FROM summary_nodes").fetchone()[0]
        stats["learnings"] = conn.execute("SELECT count(*) FROM learnings").fetchone()[0]

        # Entity types breakdown
        entity_summary = conn.execute(
            "SELECT entity_type, count(*) FROM entities GROUP BY entity_type"
        ).fetchall()
        stats["entity_summary"] = {row[0]: row[1] for row in entity_summary}

        return stats

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
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    channel="system",
                    direction="internal",
                    session_key="system:migration",
                    content=f"Legacy long-term memory:\n\n{content[:1000]}",  # Truncate if too long
                    event_type="legacy_import",
                    metadata={"source": "memory.md_migration", "importance": 0.8},
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
                        id=str(uuid.uuid4()),
                        timestamp=datetime.strptime(date_str, "%Y-%m-%d"),
                        channel="system",
                        direction="internal",
                        session_key="system:migration",
                        content=f"Legacy daily notes ({date_str}):\n\n{content[:2000]}",  # Truncate if too long
                        event_type="legacy_import",
                        metadata={"source": "daily_notes_migration", "importance": 0.6},
                    )
                    self.save_event(event)
                    stats["events_imported"] += 1
                    stats["files_processed"] += 1
                    logger.info(f"Migrated daily notes: {date_str} ({len(content)} chars)")
            except Exception as e:
                logger.warning(f"Failed to migrate {file_path}: {e}")

        logger.info(
            f"Migration complete: {stats['events_imported']} events from {stats['files_processed']} files"
        )
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
                parts.append(
                    f"- [{event.timestamp.strftime('%Y-%m-%d %H:%M')}] {event.event_type}: {event.content[:100]}"
                )

        # Get important entities
        entities = self.get_all_entities()
        important_entities = [e for e in entities if e.event_count > 2][:10]
        if important_entities:
            parts.append("\n## Key Entities")
            for entity in important_entities:
                parts.append(
                    f"- {entity.name} ({entity.entity_type}): {entity.description or 'No description'}"
                )

        # Get active learnings
        learnings = self.get_active_learnings(limit=5)
        if learnings:
            parts.append("\n## Learned Preferences")
            for learning in learnings:
                parts.append(f"- {learning.content}")

        # Get latest summary
        summaries = self.get_summary_nodes(parent_id=None)
        if summaries:
            latest = max(summaries, key=lambda s: s.last_updated or datetime.min)
            parts.append(f"\n## Conversation Summary\n{latest.summary}")

        return "\n".join(parts) if parts else ""


class MemoryStore(TurboMemoryStore):
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
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)
