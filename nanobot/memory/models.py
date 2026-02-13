"""Data models for the memory system.

This module defines all data structures used by the memory system including
events, entities, relationships, facts, and learnings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    """Immutable record of an interaction.
    
    Events form the foundation of the memory system. Every user message,
    assistant response, tool call, and observation is logged as an event.
    """
    id: str
    timestamp: datetime
    channel: str  # e.g., "cli", "telegram", "discord"
    direction: str  # "inbound", "outbound", "internal"
    event_type: str  # "message", "tool_call", "tool_result", "observation"
    content: str
    session_key: str  # Format: "channel:chat_id"
    
    # Optional fields
    parent_event_id: Optional[str] = None  # For threading (e.g., tool_result → tool_call)
    person_id: Optional[str] = None  # Entity ID if this relates to a person
    tool_name: Optional[str] = None  # For tool_call/tool_result events
    extraction_status: str = "pending"  # "pending", "complete", "skipped", "failed"
    
    # Embeddings (stored as packed bytes for efficiency)
    content_embedding: Optional[bytes] = None
    
    # Relevance tracking
    relevance_score: float = 1.0  # Decays over time unless re-mentioned
    last_accessed: Optional[datetime] = None
    
    # Flexible metadata for extensibility
    metadata: dict = field(default_factory=dict)


@dataclass
class Entity:
    """A person, organization, concept, or thing extracted from events.
    
    Entities form the nodes in the knowledge graph. Each entity has a canonical
    name, aliases, and metadata about where it was seen.
    """
    id: str
    name: str  # Canonical name
    entity_type: str  # "person", "organization", "location", "concept", "tool"
    
    # Aliases and description
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    
    # Embeddings for semantic similarity
    name_embedding: Optional[bytes] = None
    description_embedding: Optional[bytes] = None
    
    # Tracking
    source_event_ids: list[str] = field(default_factory=list)
    event_count: int = 0  # How many events mention this entity
    
    # Timestamps
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class Edge:
    """A relationship between two entities.
    
    Edges form the connections in the knowledge graph. The strength field
    allows relationships to be reinforced when mentioned multiple times.
    """
    id: str
    source_entity_id: str
    target_entity_id: str
    relation: str  # e.g., "works_at", "knows", "likes"
    relation_type: str  # "professional", "social", "technical", etc.
    
    # Relationship strength (0.0-1.0, increases with re-mentions)
    strength: float = 0.5
    
    # Tracking
    source_event_ids: list[str] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class Fact:
    """A subject-predicate-object triplet extracted from events.
    
    Facts capture specific assertions like "User prefers short emails" or
    "Project deadline is Friday". They support temporal validity.
    """
    id: str
    subject_entity_id: str
    predicate: str  # e.g., "prefers", "is_expert_in", "deadline_is"
    object_text: str  # The literal value or entity reference
    
    # If object is another entity
    object_entity_id: Optional[str] = None
    
    # Classification
    fact_type: str = "attribute"  # "relation", "attribute", "preference", "state"
    confidence: float = 0.8
    strength: float = 1.0  # Increases with re-mentions
    
    # Tracking
    source_event_ids: list[str] = field(default_factory=list)
    
    # Temporal validity (optional)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


@dataclass
class Topic:
    """A theme or subject that groups related events.
    
    Topics provide a higher-level organization of events beyond individual
    entities. They help with clustering and retrieval.
    """
    id: str
    name: str  # Topic label
    description: str = ""
    
    # Embedding for semantic similarity
    embedding: Optional[bytes] = None
    
    # Related events
    event_ids: list[str] = field(default_factory=list)
    
    # Timestamps
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class SummaryNode:
    """A node in the hierarchical summary tree.
    
    Summary nodes store pre-computed summaries at different levels:
    - Root: Overall summary
    - Channel: Per-chat-platform summary  
    - Entity: Summary of everything known about an entity
    - Topic: Summary of a theme
    """
    id: str
    node_type: str  # "root", "channel", "entity", "topic", "user_preferences"
    key: str  # e.g., "root", "channel:telegram", "entity:{id}"
    
    # Hierarchy
    parent_id: Optional[str] = None
    
    # Content
    summary: str = ""  # LLM-generated text
    summary_embedding: Optional[bytes] = None
    
    # Staleness tracking
    events_since_update: int = 0  # Incremented when new events arrive
    last_updated: Optional[datetime] = None


@dataclass  
class Learning:
    """An insight learned from user feedback or self-evaluation.
    
    Learnings capture user preferences, corrections, and patterns.
    They have a 14-day half-life by default, with re-boost on access.
    """
    id: str
    content: str  # The insight itself
    
    # Classification
    source: str  # "user_feedback", "self_evaluation"
    sentiment: str = "neutral"  # "positive", "negative", "neutral"
    confidence: float = 0.8
    
    # Application
    tool_name: Optional[str] = None  # If tool-specific
    recommendation: str = ""  # Actionable instruction
    
    # Contradiction resolution
    superseded_by: Optional[str] = None  # ID of newer learning that replaces this
    
    # Embeddings
    content_embedding: Optional[bytes] = None
    
    # Decay tracking
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None  # For decay calculation
    relevance_score: float = 1.0  # Decays over time
    
    # Access tracking (for re-boost)
    times_accessed: int = 0
    last_accessed: Optional[datetime] = None
