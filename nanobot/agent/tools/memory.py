"""Memory tools for the agent.

This module provides tools that the agent can use to query and interact
with its memory system. These tools are registered with the agent's
tool registry and can be called during conversations.

Tools provided:
- search_memory: Search for information in memory
- get_entity: Look up details about a specific entity
- get_relationships: Find connections between entities
- recall: Retrieve context about a topic
"""

from typing import Any, Optional

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.memory.retrieval import MemoryRetrieval
from nanobot.memory.store import TurboMemoryStore


class MemorySearchTool(Tool):
    """Tool to search the memory system."""
    
    def __init__(self, retrieval: MemoryRetrieval):
        self.retrieval = retrieval
    
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return (
            "Search the memory system for relevant information. "
            "Use this when you need to find facts, entities, or past conversations "
            "related to a specific topic or query."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'pricing information', 'John project')"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["semantic", "text", "hybrid"],
                    "description": "Search type: semantic (embedding-based), text (keyword), or hybrid (both)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: filter by specific channel (e.g., 'telegram', 'cli')"
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        query: str,
        search_type: str = "hybrid",
        limit: int = 10,
        channel: str = None,
        **kwargs
    ) -> str:
        """Execute memory search."""
        try:
            results = self.retrieval.search(
                query=query,
                search_type=search_type,
                limit=limit,
                channel=channel,
            )
            
            # Format results
            parts = [f"Memory search results for '{query}':\n"]
            
            if results["entities"]:
                parts.append("Entities:")
                for entity in results["entities"][:5]:
                    parts.append(f"  - {entity.name} ({entity.entity_type})")
            
            if results["events"]:
                parts.append("\nRelated conversations:")
                for event in results["events"][:3]:
                    parts.append(f"  - {event.content[:80]}...")
            
            return "\n".join(parts) if len(parts) > 1 else f"No results found for '{query}'."
            
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return f"Error searching memory: {e}"


class GetEntityTool(Tool):
    """Tool to get information about a specific entity."""
    
    def __init__(self, retrieval: MemoryRetrieval):
        self.retrieval = retrieval
    
    @property
    def name(self) -> str:
        return "get_entity"
    
    @property
    def description(self) -> str:
        return (
            "Get detailed information about a specific entity (person, organization, concept). "
            "Use this when the user mentions someone or something by name and you need "
            "to recall what you know about them."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the entity (e.g., 'John Smith', 'Google', 'Python')"
                },
                "include_facts": {
                    "type": "boolean",
                    "description": "Whether to include known facts about the entity",
                    "default": True
                },
                "include_relationships": {
                    "type": "boolean",
                    "description": "Whether to include relationships with other entities",
                    "default": True
                }
            },
            "required": ["name"]
        }
    
    async def execute(
        self,
        name: str,
        include_facts: bool = True,
        include_relationships: bool = True,
        **kwargs
    ) -> str:
        """Execute entity lookup."""
        try:
            # Find entity
            entity = self.retrieval.get_entity_by_name(name)
            
            if not entity:
                return f"I don't have any information about '{name}' in my memory."
            
            # Build response
            parts = [f"Information about {entity.name}:\n"]
            parts.append(f"Type: {entity.entity_type}")
            parts.append(f"Mentions: {entity.event_count} times")
            
            if entity.aliases:
                parts.append(f"Also known as: {', '.join(entity.aliases)}")
            
            # Add facts
            if include_facts:
                facts = self.retrieval.get_entity_facts(entity.id)
                if facts:
                    parts.append("\nKnown facts:")
                    for fact in facts[:5]:
                        parts.append(f"  • {fact.predicate}: {fact.object_text}")
            
            # Add relationships
            if include_relationships:
                relationships = self.retrieval.get_relationships(entity.id)
                if relationships:
                    parts.append("\nRelationships:")
                    for rel in relationships[:5]:
                        parts.append(f"  • {rel['relation_type']} with {rel['entity'].name}")
            
            return "\n".join(parts)
            
        except Exception as e:
            logger.error(f"Entity lookup failed: {e}")
            return f"Error looking up entity: {e}"


class GetRelationshipsTool(Tool):
    """Tool to get relationships between entities."""
    
    def __init__(self, retrieval: MemoryRetrieval):
        self.retrieval = retrieval
    
    @property
    def name(self) -> str:
        return "get_relationships"
    
    @property
    def description(self) -> str:
        return (
            "Find relationships and connections between entities. "
            "Use this to understand how people, organizations, or concepts are connected."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity to find relationships for"
                },
                "relation_type": {
                    "type": "string",
                    "description": "Optional: filter by relationship type (e.g., 'works_at', 'friend')"
                },
                "min_strength": {
                    "type": "number",
                    "description": "Minimum relationship strength (0.0-1.0)",
                    "default": 0.5
                }
            },
            "required": ["entity_name"]
        }
    
    async def execute(
        self,
        entity_name: str,
        relation_type: str = None,
        min_strength: float = 0.5,
        **kwargs
    ) -> str:
        """Execute relationship lookup."""
        try:
            # Find entity
            entity = self.retrieval.get_entity_by_name(entity_name)
            
            if not entity:
                return f"I don't have any information about '{entity_name}'."
            
            # Get relationships
            relationships = self.retrieval.get_relationships(
                entity.id,
                relation_type=relation_type,
                min_strength=min_strength,
            )
            
            if not relationships:
                return f"No known relationships found for {entity.name}."
            
            # Format results
            parts = [f"Relationships for {entity.name}:\n"]
            
            for rel in relationships:
                parts.append(
                    f"  • {rel['relation_type']} → {rel['entity'].name} "
                    f"(strength: {rel['strength']:.2f})"
                )
            
            return "\n".join(parts)
            
        except Exception as e:
            logger.error(f"Relationship lookup failed: {e}")
            return f"Error finding relationships: {e}"


class RecallTool(Tool):
    """Tool to recall relevant context about a topic."""
    
    def __init__(self, retrieval: MemoryRetrieval):
        self.retrieval = retrieval
    
    @property
    def name(self) -> str:
        return "recall"
    
    @property
    def description(self) -> str:
        return (
            "Recall relevant context and information about a specific topic. "
            "Use this when you need to remember details, facts, or past discussions "
            "about something the user is asking about."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to recall information about (e.g., 'project deadline', 'vacation plans')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of facts/events to include",
                    "default": 5
                }
            },
            "required": ["topic"]
        }
    
    async def execute(
        self,
        topic: str,
        limit: int = 5,
        **kwargs
    ) -> str:
        """Execute recall."""
        try:
            result = self.retrieval.recall(topic, limit=limit)
            return result
            
        except Exception as e:
            logger.error(f"Recall failed: {e}")
            return f"Error recalling information: {e}"


def create_memory_tools(store: TurboMemoryStore, retrieval: MemoryRetrieval) -> list[Tool]:
    """
    Create all memory tools for the agent.
    
    Args:
        store: TurboMemoryStore instance
        retrieval: MemoryRetrieval instance
        
    Returns:
        List of memory tools
    """
    return [
        MemorySearchTool(retrieval),
        GetEntityTool(retrieval),
        GetRelationshipsTool(retrieval),
        RecallTool(retrieval),
    ]
