"""nanobot Memory System

A lightweight, local-first memory system for the nanobot AI assistant.
Provides semantic search, entity tracking, and knowledge graph capabilities.
"""

from nanobot.memory.models import (
    Event,
    Entity,
    Edge,
    Fact,
    Topic,
    SummaryNode,
    Learning,
)
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.embeddings import (
    EmbeddingProvider,
    pack_embedding,
    unpack_embedding,
    cosine_similarity,
)
from nanobot.memory.background import (
    ActivityTracker,
    BackgroundProcessor,
)
from nanobot.memory.extraction import (
    Gliner2Extractor,
    ExtractionResult,
    extract_entities,
)
from nanobot.memory.graph import (
    KnowledgeGraphManager,
    create_entity_resolver,
)
from nanobot.memory.summaries import (
    SummaryTreeManager,
    create_summary_manager,
)
from nanobot.memory.context import (
    ContextAssembler,
    ContextBudget,
    create_context_assembler,
)
from nanobot.memory.retrieval import (
    MemoryRetrieval,
    create_retrieval,
)
from nanobot.memory.learning import (
    LearningManager,
    FeedbackDetector,
    create_learning_manager,
)
from nanobot.memory.preferences import (
    PreferencesAggregator,
    create_preferences_aggregator,
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
