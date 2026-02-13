"""Memory retrieval interface for agent queries.

This module provides query capabilities for the memory system,
allowing the agent to search, retrieve, and traverse the knowledge graph.

Provides:
- Semantic search over events and entities
- Entity lookup and relationship traversal
- Fact retrieval
- Context-aware recall
"""

from typing import Optional

from loguru import logger

from nanobot.memory.models import Event, Entity, Edge, Fact
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.embeddings import EmbeddingProvider


class MemoryRetrieval:
    """
    Retrieval interface for memory queries.
    
    Provides methods for the agent to query its memory:
    - Search: Find relevant events/entities by text or embedding
    - Lookup: Get specific entities or facts
    - Traverse: Follow relationships in the graph
    - Recall: Context-aware retrieval
    """
    
    def __init__(
        self,
        store: TurboMemoryStore,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        """
        Initialize memory retrieval.
        
        Args:
            store: TurboMemoryStore for database access
            embedding_provider: Optional embedding provider for semantic search
        """
        self.store = store
        self.embedding_provider = embedding_provider
        
        logger.info("MemoryRetrieval initialized")
    
    def search(
        self,
        query: str,
        search_type: str = "hybrid",  # "semantic", "text", "hybrid"
        limit: int = 10,
        channel: str = None,
    ) -> dict:
        """
        Search memory for relevant information.
        
        Args:
            query: Search query
            search_type: Type of search (semantic, text, hybrid)
            limit: Maximum results
            channel: Optional channel filter
            
        Returns:
            Dict with events, entities, and facts
        """
        results = {
            "events": [],
            "entities": [],
            "facts": [],
        }
        
        if search_type in ["semantic", "hybrid"] and self.embedding_provider:
            # Semantic search using embeddings
            query_embedding = self.embedding_provider.embed(query)
            
            # Search events
            events = self.store.search_similar_events(query_embedding, limit=limit)
            results["events"] = events
            
            # Search entities
            entities = self.store.search_similar_entities(query_embedding, limit=limit)
            results["entities"] = entities
        
        if search_type in ["text", "hybrid"]:
            # Text search
            text_events = self.store.search_events_by_text(query, limit=limit)
            results["events"].extend(text_events)
            
            # Find entities by name
            text_entities = self.store.search_entities_by_name(query, limit=limit)
            results["entities"].extend(text_entities)
        
        # Remove duplicates
        seen_event_ids = set()
        unique_events = []
        for e in results["events"]:
            if e.id not in seen_event_ids:
                seen_event_ids.add(e.id)
                unique_events.append(e)
        results["events"] = unique_events[:limit]
        
        seen_entity_ids = set()
        unique_entities = []
        for e in results["entities"]:
            if e.id not in seen_entity_ids:
                seen_entity_ids.add(e.id)
                unique_entities.append(e)
        results["entities"] = unique_entities[:limit]
        
        return results
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """
        Get an entity by ID.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            Entity if found, None otherwise
        """
        return self.store.get_entity(entity_id)
    
    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """
        Get an entity by name.
        
        Args:
            name: Entity name
            
        Returns:
            Entity if found, None otherwise
        """
        return self.store.find_entity_by_name(name)
    
    def get_entity_facts(self, entity_id: str) -> list[Fact]:
        """
        Get all facts about an entity.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            List of facts
        """
        return self.store.get_facts_for_entity(entity_id)
    
    def get_relationships(
        self,
        entity_id: str,
        relation_type: str = None,
        min_strength: float = 0.5,
    ) -> list[dict]:
        """
        Get relationships for an entity.
        
        Args:
            entity_id: Entity ID
            relation_type: Optional filter by relation type
            min_strength: Minimum relationship strength
            
        Returns:
            List of relationships with connected entities
        """
        edges = self.store.get_edges_for_entity(entity_id, min_strength=min_strength)
        
        relationships = []
        for edge in edges:
            if relation_type and edge.relation_type != relation_type:
                continue
            
            # Determine the other entity
            if edge.source_entity_id == entity_id:
                other_id = edge.target_entity_id
                direction = "outgoing"
            else:
                other_id = edge.source_entity_id
                direction = "incoming"
            
            other_entity = self.store.get_entity(other_id)
            if other_entity:
                relationships.append({
                    "entity": other_entity,
                    "relation_type": edge.relation_type,
                    "strength": edge.strength,
                    "direction": direction,
                })
        
        return relationships
    
    def recall(
        self,
        topic: str,
        channel: str = None,
        limit: int = 5,
    ) -> str:
        """
        Recall relevant context for a topic.
        
        Args:
            topic: Topic to recall information about
            channel: Optional channel context
            limit: Maximum facts/events to include
            
        Returns:
            Formatted context string
        """
        # Search for relevant entities
        search_results = self.search(topic, limit=limit)
        
        parts = []
        
        # Add entity information
        if search_results["entities"]:
            parts.append(f"Relevant entities about '{topic}':")
            for entity in search_results["entities"]:
                parts.append(f"  - {entity.name} ({entity.entity_type})")
                
                # Add facts
                facts = self.get_entity_facts(entity.id)
                for fact in facts[:3]:  # Top 3 facts
                    parts.append(f"    • {fact.predicate}: {fact.object_text}")
        
        # Add recent events
        if search_results["events"]:
            parts.append(f"\nRecent mentions of '{topic}':")
            for event in search_results["events"][:3]:
                parts.append(f"  - {event.content[:100]}...")
        
        return "\n".join(parts) if parts else f"No information found about '{topic}'."
    
    def get_recent_events(
        self,
        channel: str = None,
        limit: int = 10,
        event_type: str = None,
    ) -> list[Event]:
        """
        Get recent events.
        
        Args:
            channel: Optional channel filter
            limit: Maximum events
            event_type: Optional event type filter
            
        Returns:
            List of recent events
        """
        if channel:
            return self.store.get_events_for_channel(channel, limit=limit)
        else:
            return self.store.get_recent_events(limit=limit)
    
    def get_all_entities(
        self,
        entity_type: str = None,
        limit: int = 100,
    ) -> list[Entity]:
        """
        Get all entities, optionally filtered by type.
        
        Args:
            entity_type: Optional type filter
            limit: Maximum entities
            
        Returns:
            List of entities
        """
        if entity_type:
            return self.store.get_entities_by_type(entity_type, limit=limit)
        else:
            return self.store.get_all_entities(limit=limit)


def create_retrieval(
    store: TurboMemoryStore,
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> MemoryRetrieval:
    """
    Factory function to create MemoryRetrieval.
    
    Args:
        store: TurboMemoryStore instance
        embedding_provider: Optional embedding provider
        
    Returns:
        MemoryRetrieval instance
    """
    return MemoryRetrieval(store, embedding_provider)
