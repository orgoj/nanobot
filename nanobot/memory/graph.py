"""Knowledge graph operations for entity resolution and relationship management.

This module provides graph operations including:
- Entity resolution (merging duplicates, managing aliases)
- Edge management (creating, updating, deduplicating relationships)
- Fact deduplication and management
- Graph traversal and queries
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from loguru import logger

from nanobot.memory.models import Entity, Edge, Fact
from nanobot.memory.store import TurboMemoryStore


class KnowledgeGraphManager:
    """
    Manages the knowledge graph operations.
    
    Handles entity resolution (preventing duplicates), edge management,
    and fact deduplication. Works on top of TurboMemoryStore.
    """
    
    def __init__(self, store: TurboMemoryStore):
        """
        Initialize the knowledge graph manager.
        
        Args:
            store: TurboMemoryStore instance for database operations
        """
        self.store = store
    
    def resolve_entity(self, name: str, entity_type: str) -> Optional[Entity]:
        """
        Find or create an entity, handling duplicates via name matching.
        
        Args:
            name: Entity name to resolve
            entity_type: Type of entity (person, organization, etc.)
            
        Returns:
            Existing entity if found, None if should create new
        """
        # Normalize name for matching
        normalized_name = self._normalize_name(name)
        
        # Try exact match first
        existing = self._find_by_exact_name(normalized_name, entity_type)
        if existing:
            return existing
        
        # Try fuzzy match on name and aliases
        existing = self._find_by_fuzzy_match(normalized_name, entity_type)
        if existing:
            # Add this name as an alias
            self._add_alias(existing, name)
            return existing
        
        # No match found - should create new entity
        return None
    
    def merge_entities(self, primary_id: str, duplicate_id: str) -> Entity:
        """
        Merge two entities into one, consolidating all relationships and facts.
        
        Args:
            primary_id: ID of entity to keep
            duplicate_id: ID of entity to merge into primary
            
        Returns:
            Updated primary entity
        """
        primary = self.store.get_entity(primary_id)
        duplicate = self.store.get_entity(duplicate_id)
        
        if not primary or not duplicate:
            raise ValueError("One or both entities not found")
        
        # Merge aliases
        for alias in duplicate.aliases:
            if alias not in primary.aliases:
                primary.aliases.append(alias)
        
        # Merge metadata
        primary.metadata.update(duplicate.metadata)
        
        # Update all edges pointing to duplicate
        edges = self.store.get_edges_for_entity(duplicate_id)
        for edge in edges:
            if edge.source_entity_id == duplicate_id:
                edge.source_entity_id = primary_id
            if edge.target_entity_id == duplicate_id:
                edge.target_entity_id = primary_id
            self.store.update_edge(edge)
        
        # Update all facts for duplicate
        facts = self.store.get_facts_for_entity(duplicate_id)
        for fact in facts:
            if fact.subject_id == duplicate_id:
                fact.subject_id = primary_id
            if fact.object_id == duplicate_id:
                fact.object_id = primary_id
            self.store.update_fact(fact)
        
        # Increment mention count
        primary.mention_count += duplicate.mention_count
        primary.last_seen = datetime.now()
        
        # Save primary and delete duplicate
        self.store.update_entity(primary)
        self.store.delete_entity(duplicate_id)
        
        logger.info(f"Merged entity {duplicate_id} into {primary_id}")
        
        return primary
    
    def create_or_update_edge(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        confidence: float = 0.8
    ) -> Edge:
        """
        Create or update an edge between two entities.
        
        If an edge already exists between these entities with the same
        relation type, update its strength. Otherwise create new.
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relation_type: Type of relationship
            confidence: Confidence score (0-1)
            
        Returns:
            Created or updated Edge
        """
        # Check for existing edge
        existing = self.store.get_edge(source_id, target_id, relation_type)
        
        if existing:
            # Update existing edge
            existing.strength = min(1.0, existing.strength + 0.1)  # Boost strength
            existing.evidence_count += 1
            existing.last_updated = datetime.now()
            if confidence > existing.confidence:
                existing.confidence = confidence
            
            self.store.update_edge(existing)
            return existing
        else:
            # Create new edge
            edge = Edge(
                id=str(uuid4()),
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type,
                strength=confidence,
                confidence=confidence,
                evidence_count=1,
                first_seen=datetime.now(),
                last_updated=datetime.now(),
            )
            
            self.store.create_edge(edge)
            return edge
    
    def deduplicate_fact(self, fact: Fact) -> Optional[Fact]:
        """
        Check if a fact already exists and update or return existing.
        
        Args:
            fact: Fact to deduplicate
            
        Returns:
            Existing fact if found, None if should create new
        """
        # Look for similar facts
        existing_facts = self.store.get_facts_for_subject(fact.subject_id)
        
        for existing in existing_facts:
            # Check if same predicate and similar object
            if (existing.predicate == fact.predicate and
                self._similar_objects(existing.object_value, fact.object_value)):
                
                # Update confidence if new fact is more confident
                if fact.confidence > existing.confidence:
                    existing.confidence = fact.confidence
                    existing.object_value = fact.object_value
                    self.store.update_fact(existing)
                
                # Increment evidence count
                existing.evidence_count = existing.evidence_count + 1
                existing.last_seen = datetime.now()
                self.store.update_fact(existing)
                
                return existing
        
        return None
    
    def get_entity_network(
        self,
        entity_id: str,
        depth: int = 1,
        min_strength: float = 0.5
    ) -> dict:
        """
        Get the network of entities connected to a given entity.
        
        Args:
            entity_id: Starting entity ID
            depth: How many hops to traverse (1 = direct connections)
            min_strength: Minimum edge strength to include
            
        Returns:
            Dict with 'entity', 'connections', and 'related_facts'
        """
        entity = self.store.get_entity(entity_id)
        if not entity:
            return {}
        
        connections = []
        seen_ids = {entity_id}
        
        # Get direct connections
        edges = self.store.get_edges_for_entity(entity_id, min_strength=min_strength)
        
        for edge in edges:
            other_id = (edge.target_entity_id 
                       if edge.source_entity_id == entity_id 
                       else edge.source_entity_id)
            
            if other_id not in seen_ids:
                other_entity = self.store.get_entity(other_id)
                if other_entity:
                    connections.append({
                        'entity': other_entity,
                        'edge': edge,
                        'relation': edge.relation_type,
                    })
                    seen_ids.add(other_id)
        
        # Get facts about this entity
        facts = self.store.get_facts_for_entity(entity_id)
        
        return {
            'entity': entity,
            'connections': connections,
            'facts': facts,
            'total_connections': len(connections),
            'total_facts': len(facts),
        }
    
    def find_similar_entities(self, entity_id: str, threshold: float = 0.7) -> list[Entity]:
        """
        Find entities similar to a given entity using embeddings.
        
        Args:
            entity_id: Entity to compare
            threshold: Minimum similarity score (0-1)
            
        Returns:
            List of similar entities
        """
        entity = self.store.get_entity(entity_id)
        if not entity or not entity.embedding:
            return []
        
        # Search for similar entities
        similar = self.store.search_similar_entities(
            entity.embedding,
            limit=10,
            threshold=threshold
        )
        
        # Exclude the entity itself
        return [e for e in similar if e.id != entity_id]
    
    def update_entity_embedding(self, entity_id: str) -> Optional[Entity]:
        """
        Update an entity's embedding based on its name, aliases, and related text.
        
        Args:
            entity_id: Entity to update
            
        Returns:
            Updated entity
        """
        entity = self.store.get_entity(entity_id)
        if not entity:
            return None
        
        # Build text from entity info
        texts = [entity.name] + entity.aliases
        
        # Add related facts
        facts = self.store.get_facts_for_entity(entity_id)
        for fact in facts:
            texts.append(f"{fact.predicate} {fact.object_value}")
        
        # Combine and embed
        combined_text = " ".join(texts)
        
        # Generate embedding (requires embedding provider)
        from nanobot.memory.embeddings import EmbeddingProvider
        from nanobot.config.schema import MemoryConfig
        
        config = MemoryConfig()
        provider = EmbeddingProvider(config.embedding)
        embedding = provider.embed(combined_text)
        
        # Update entity
        entity.embedding = embedding
        entity.embedding_updated_at = datetime.now()
        
        self.store.update_entity(entity)
        
        return entity
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for matching."""
        # Convert to lowercase
        name = name.lower()
        
        # Remove common titles
        titles = ['mr', 'mrs', 'ms', 'dr', 'prof']
        for title in titles:
            if name.startswith(title + ' '):
                name = name[len(title)+1:]
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        return name
    
    def _find_by_exact_name(self, name: str, entity_type: str) -> Optional[Entity]:
        """Find entity by exact name match."""
        entities = self.store.get_entities_by_type(entity_type)
        for entity in entities:
            if self._normalize_name(entity.name) == name:
                return entity
        return None
    
    def _find_by_fuzzy_match(self, name: str, entity_type: str) -> Optional[Entity]:
        """Find entity by fuzzy name matching."""
        entities = self.store.get_entities_by_type(entity_type)
        
        for entity in entities:
            # Check name similarity
            if self._name_similarity(entity.name, name) > 0.8:
                return entity
            
            # Check aliases
            for alias in entity.aliases:
                if self._name_similarity(alias, name) > 0.8:
                    return entity
        
        return None
    
    def _name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names."""
        # Simple implementation - can be enhanced with more sophisticated algorithms
        name1 = self._normalize_name(name1)
        name2 = self._normalize_name(name2)
        
        if name1 == name2:
            return 1.0
        
        # Check if one contains the other
        if name1 in name2 or name2 in name1:
            return 0.9
        
        # Word overlap
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def _add_alias(self, entity: Entity, alias: str):
        """Add an alias to an entity if not already present."""
        alias_normalized = self._normalize_name(alias)
        
        # Check if already an alias
        for existing in entity.aliases:
            if self._normalize_name(existing) == alias_normalized:
                return
        
        entity.aliases.append(alias)
        self.store.update_entity(entity)
        
        logger.debug(f"Added alias '{alias}' to entity {entity.name}")
    
    def _similar_objects(self, obj1: str, obj2: str) -> bool:
        """Check if two object values are similar."""
        obj1 = obj1.lower().strip()
        obj2 = obj2.lower().strip()
        
        if obj1 == obj2:
            return True
        
        # Check word overlap for longer strings
        if len(obj1) > 10 and len(obj2) > 10:
            words1 = set(obj1.split())
            words2 = set(obj2.split())
            
            if words1 and words2:
                intersection = words1 & words2
                union = words1 | words2
                similarity = len(intersection) / len(union)
                return similarity > 0.7
        
        return False


def create_entity_resolver(store: TurboMemoryStore) -> KnowledgeGraphManager:
    """
    Factory function to create a KnowledgeGraphManager.
    
    Args:
        store: TurboMemoryStore instance
        
    Returns:
        KnowledgeGraphManager instance
    """
    return KnowledgeGraphManager(store)
