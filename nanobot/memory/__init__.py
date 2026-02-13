"""nanobot Memory System

A lightweight, local-first memory system for the nanobot AI assistant.
Provides semantic search, entity tracking, and knowledge graph capabilities.
"""

from nanobot.memory.background import (
    ActivityTracker,
    BackgroundProcessor,
)
from nanobot.memory.context import (
    ContextAssembler,
    ContextBudget,
    create_context_assembler,
)
from nanobot.memory.embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    pack_embedding,
    unpack_embedding,
)
from nanobot.memory.extraction import (
    ExtractionResult,
    Gliner2Extractor,
    extract_entities,
)
from nanobot.memory.graph import (
    KnowledgeGraphManager,
    create_entity_resolver,
)
from nanobot.memory.learning import (
    FeedbackDetector,
    LearningManager,
    create_learning_manager,
)
from nanobot.memory.models import (
    Edge,
    Entity,
    Event,
    Fact,
    Learning,
    SummaryNode,
    Topic,
)
from nanobot.memory.preferences import (
    PreferencesAggregator,
    create_preferences_aggregator,
)
from nanobot.memory.retrieval import (
    MemoryRetrieval,
    create_retrieval,
)
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.summaries import (
    SummaryTreeManager,
    create_summary_manager,
)

__all__ = [
    "Event",
    "Entity",
    "Edge",
    "Fact",
    "Topic",
    "SummaryNode",
    "Learning",
    "TurboMemoryStore",
    "EmbeddingProvider",
    "pack_embedding",
    "unpack_embedding",
    "cosine_similarity",
    "ActivityTracker",
    "BackgroundProcessor",
    "Gliner2Extractor",
    "ExtractionResult",
    "extract_entities",
    "KnowledgeGraphManager",
    "create_entity_resolver",
    "SummaryTreeManager",
    "create_summary_manager",
    "ContextAssembler",
    "ContextBudget",
    "create_context_assembler",
    "MemoryRetrieval",
    "create_retrieval",
    "LearningManager",
    "FeedbackDetector",
    "create_learning_manager",
    "PreferencesAggregator",
    "create_preferences_aggregator",
]
