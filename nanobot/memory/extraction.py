"""Entity extraction using GLiNER2 and spaCy.

This module provides entity and relationship extraction from text.
Uses GLiNER2 as primary extractor with spaCy as fallback.
"""

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from nanobot.config.schema import ExtractionConfig
from nanobot.memory.models import Event, Entity, Edge, Fact


@dataclass
class ExtractionResult:
    """Result of entity extraction from text."""
    entities: list[Entity]
    edges: list[Edge]
    facts: list[Fact]


class Gliner2Extractor:
    """
    GLiNER2-based entity and relationship extractor.
    
    GLiNER2 provides state-of-the-art NER and relation extraction
    in a single forward pass.
    """
    
    def __init__(self, config: ExtractionConfig):
        """
        Initialize the GLiNER2 extractor.
        
        Args:
            config: Extraction configuration
        """
        self.config = config
        self._extractor = None
        
        logger.info(f"GLiNER2Extractor initialized (model: {config.gliner2_model})")
    
    def _ensure_model(self):
        """Lazy load the GLiNER2 model."""
        if self._extractor is None:
            try:
                from gliner2 import GLiNER2
                
                logger.info(f"Loading GLiNER2 model: {self.config.gliner2_model}")
                self._extractor = GLiNER2(model_name=self.config.gliner2_model)
                logger.info("GLiNER2 model loaded successfully")
            except ImportError:
                logger.error("gliner2 package not installed. Install with: pip install gliner2")
                raise
            except Exception as e:
                logger.error(f"Failed to load GLiNER2 model: {e}")
                raise
    
    async def extract(self, event: Event) -> ExtractionResult:
        """
        Extract entities, relationships, and facts from an event.
        
        Args:
            event: Event to extract from
            
        Returns:
            ExtractionResult with entities, edges, and facts
        """
        self._ensure_model()
        
        text = event.content
        if not text or len(text.strip()) < 3:
            return ExtractionResult(entities=[], edges=[], facts=[])
        
        try:
            # Use GLiNER2 for unified extraction
            # This extracts entities, relationships, and structured data in one pass
            extraction = self._extractor.extract_all(text)
            
            entities = []
            edges = []
            facts = []
            
            # Convert GLiNER2 entities to our Entity model
            for ent in extraction.get("entities", []):
                entity = self._convert_entity(ent, event)
                if entity:
                    entities.append(entity)
            
            # Convert GLiNER2 relations to our Edge model
            for rel in extraction.get("relations", []):
                edge = self._convert_relation(rel, event, entities)
                if edge:
                    edges.append(edge)
            
            # Extract facts from text patterns
            facts = self._extract_facts(text, event, entities)
            
            return ExtractionResult(entities=entities, edges=edges, facts=facts)
            
        except Exception as e:
            logger.error(f"GLiNER2 extraction failed: {e}")
            return ExtractionResult(entities=[], edges=[], facts=[])
    
    def _convert_entity(self, gliner_entity: dict, event: Event) -> Optional[Entity]:
        """Convert GLiNER2 entity to our Entity model."""
        import uuid
        from datetime import datetime
        
        entity_type = gliner_entity.get("label", "concept")
        name = gliner_entity.get("text", "").strip()
        
        if not name:
            return None
        
        # Normalize entity type
        entity_type = self._normalize_entity_type(entity_type)
        
        return Entity(
            id=str(uuid.uuid4()),
            name=name,
            entity_type=entity_type,
            aliases=[name.lower()],  # Store normalized version
            description="",
            source_event_ids=[event.id],
            event_count=1,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
    
    def _convert_relation(
        self,
        gliner_relation: dict,
        event: Event,
        entities: list[Entity]
    ) -> Optional[Edge]:
        """Convert GLiNER2 relation to our Edge model."""
        import uuid
        from datetime import datetime
        
        source_text = gliner_relation.get("source", "")
        target_text = gliner_relation.get("target", "")
        relation = gliner_relation.get("relation", "related_to")
        
        # Find matching entities
        source_entity = self._find_entity_by_name(source_text, entities)
        target_entity = self._find_entity_by_name(target_text, entities)
        
        if not source_entity or not target_entity:
            return None
        
        relation_type = self._classify_relation(relation)
        
        return Edge(
            id=str(uuid.uuid4()),
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relation=relation,
            relation_type=relation_type,
            strength=0.7,  # Default strength for new relations
            source_event_ids=[event.id],
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
    
    def _extract_facts(
        self,
        text: str,
        event: Event,
        entities: list[Entity]
    ) -> list[Fact]:
        """Extract facts from text using pattern matching."""
        import uuid
        from datetime import datetime
        
        facts = []
        
        # Pattern: "I prefer X" or "I like X" or "I want X"
        preference_patterns = [
            (r"I\s+(?:prefer|like|want|need)\s+(.+?)(?:\.|,|;|$)", "prefers"),
            (r"My\s+(?:favorite|preferred)\s+(?:is|are)\s+(.+?)(?:\.|,|;|$)", "prefers"),
            (r"I\s+(?:don't|do not)\s+(?:like|want|prefer)\s+(.+?)(?:\.|,|;|$)", "dislikes"),
        ]
        
        for pattern, predicate in preference_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                object_text = match.group(1).strip()
                
                # Find the user entity (or create reference)
                user_entity = self._find_entity_by_type("person", entities)
                if user_entity:
                    fact = Fact(
                        id=str(uuid.uuid4()),
                        subject_entity_id=user_entity.id,
                        predicate=predicate,
                        object_text=object_text,
                        fact_type="preference",
                        confidence=0.8,
                        source_event_ids=[event.id],
                        created_at=datetime.now(),
                    )
                    facts.append(fact)
        
        return facts
    
    def _normalize_entity_type(self, entity_type: str) -> str:
        """Normalize entity type to standard categories."""
        entity_type = entity_type.lower()
        
        # Map common GLiNER2 types to our types
        type_mapping = {
            "person": "person",
            "people": "person",
            "organization": "organization",
            "org": "organization",
            "company": "organization",
            "location": "location",
            "place": "location",
            "gpe": "location",
            "concept": "concept",
            "topic": "concept",
            "technology": "concept",
            "programming_language": "concept",
            "framework": "concept",
            "tool": "tool",
            "software": "tool",
        }
        
        return type_mapping.get(entity_type, "concept")
    
    def _find_entity_by_name(self, name: str, entities: list[Entity]) -> Optional[Entity]:
        """Find entity by name (case-insensitive)."""
        name_lower = name.lower()
        for entity in entities:
            if entity.name.lower() == name_lower or name_lower in entity.aliases:
                return entity
        return None
    
    def _find_entity_by_type(self, entity_type: str, entities: list[Entity]) -> Optional[Entity]:
        """Find first entity of a given type."""
        for entity in entities:
            if entity.entity_type == entity_type:
                return entity
        return None
    
    def _classify_relation(self, relation: str) -> str:
        """Classify relation type."""
        relation = relation.lower()
        
        if any(word in relation for word in ["work", "employ", "job"]):
            return "professional"
        elif any(word in relation for word in ["friend", "family", "know", "like"]):
            return "social"
        elif any(word in relation for word in ["use", "build", "create", "develop"]):
            return "technical"
        else:
            return "general"


async def extract_entities(event: Event, config: ExtractionConfig) -> ExtractionResult:
    """
    Extract entities from an event using GLiNER2.
    
    This is the main entry point for extraction. Uses GLiNER2 for
    state-of-the-art NER, relationship extraction, and fact extraction.
    
    Args:
        event: Event to extract from
        config: Extraction configuration (provider must be "gliner2")
        
    Returns:
        ExtractionResult with extracted entities, edges, and facts
    """
    if config.provider != "gliner2":
        logger.warning(f"Unsupported extraction provider: {config.provider}. Using GLiNER2.")
    
    extractor = Gliner2Extractor(config)
    
    try:
        return await extractor.extract(event)
    except Exception as e:
        logger.error(f"Extraction failed for event {event.id}: {e}")
        return ExtractionResult(entities=[], edges=[], facts=[])
