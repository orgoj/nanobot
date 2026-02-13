"""Context assembly for memory integration with the agent.

This module implements Phase 5 of the memory proposal:
- Token-budgeted context assembly from summaries
- Memory-aware system prompt generation
- Budget allocation across different memory sections
- Integration with agent context building

The context assembler takes pre-computed summaries and assembles them
into a context string that fits within the LLM's token budget.
"""

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from nanobot.memory.models import SummaryNode, Entity
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.summaries import SummaryTreeManager


@dataclass
class ContextBudget:
    """Token budget allocation for different memory sections."""
    total: int = 4000  # Total token budget for memory context
    identity: int = 200  # Bot identity/persona
    state: int = 150  # Current conversation state
    knowledge: int = 500  # General knowledge from summaries
    channel: int = 300  # Channel-specific context
    entities: int = 400  # Entity summaries (per-entity)
    topics: int = 400  # Topic summaries
    preferences: int = 300  # User preferences
    learnings: int = 200  # Learned insights
    recent: int = 400  # Recent events
    
    def validate(self):
        """Ensure budget doesn't exceed total."""
        total_used = (
            self.identity + self.state + self.knowledge +
            self.channel + self.entities + self.topics +
            self.preferences + self.learnings + self.recent
        )
        if total_used > self.total:
            # Proportionally reduce each section
            ratio = self.total / total_used
            for key in ['identity', 'state', 'knowledge', 'channel', 
                       'entities', 'topics', 'preferences', 'learnings', 'recent']:
                setattr(self, key, int(getattr(self, key) * ratio))


class ContextAssembler:
    """
    Assembles memory context for the agent from pre-computed summaries.
    
    This class takes the hierarchical summaries and assembles them into
    a context string that fits within the token budget. It prioritizes
    the most relevant information based on the current conversation.
    """
    
    def __init__(
        self,
        store: TurboMemoryStore,
        summary_manager: SummaryTreeManager,
        budget: Optional[ContextBudget] = None,
    ):
        """
        Initialize the context assembler.
        
        Args:
            store: TurboMemoryStore for database access
            summary_manager: SummaryTreeManager for summary access
            budget: Token budget allocation (uses default if None)
        """
        self.store = store
        self.summary_manager = summary_manager
        self.budget = budget or ContextBudget()
        self.budget.validate()
        
        logger.info(f"ContextAssembler initialized (budget: {self.budget.total} tokens)")
    
    def assemble_context(
        self,
        channel: str,
        entity_ids: list[str] = None,
        recent_event_ids: list[str] = None,
        include_preferences: bool = True,
    ) -> str:
        """
        Assemble memory context from summaries.
        
        Args:
            channel: Current conversation channel
            entity_ids: Entity IDs mentioned in current conversation
            recent_event_ids: Recent event IDs to include
            include_preferences: Whether to include user preferences
            
        Returns:
            Assembled context string
        """
        sections = []
        remaining_budget = self.budget.total
        
        # Section 1: Identity (always include)
        identity_context = self._get_identity_context()
        if identity_context:
            sections.append(("IDENTITY", identity_context, self.budget.identity))
            remaining_budget -= self.budget.identity
        
        # Section 2: Channel Context
        channel_context = self._get_channel_context(channel)
        if channel_context:
            sections.append(("CHANNEL", channel_context, self.budget.channel))
            remaining_budget -= self.budget.channel
        
        # Section 3: Entity Context (prioritized by relevance)
        if entity_ids:
            entity_context = self._get_entity_context(entity_ids[:5])  # Top 5
            if entity_context:
                sections.append(("ENTITIES", entity_context, self.budget.entities))
                remaining_budget -= self.budget.entities
        
        # Section 4: User Preferences (if enabled)
        if include_preferences:
            prefs_context = self._get_preferences_context()
            if prefs_context:
                sections.append(("PREFERENCES", prefs_context, self.budget.preferences))
                remaining_budget -= self.budget.preferences
        
        # Section 5: Recent Events
        if recent_event_ids:
            recent_context = self._get_recent_context(recent_event_ids[:10])  # Top 10
            if recent_context:
                sections.append(("RECENT", recent_context, self.budget.recent))
                remaining_budget -= self.budget.recent
        
        # Section 6: Knowledge (general summaries)
        if remaining_budget > 0:
            knowledge_context = self._get_knowledge_context(
                max_tokens=min(remaining_budget, self.budget.knowledge)
            )
            if knowledge_context:
                sections.append(("KNOWLEDGE", knowledge_context, len(knowledge_context) // 4))
        
        # Assemble final context
        return self._format_sections(sections)
    
    def _get_identity_context(self) -> str:
        """Get bot identity context."""
        return """You are nanobot, an AI assistant with persistent memory.
You have access to a knowledge graph of entities, relationships, and facts from past conversations.
Use this context to provide personalized and informed responses."""
    
    def _get_channel_context(self, channel: str) -> str:
        """Get channel-specific context from summary tree."""
        channel_node = self.store.get_summary_node(f"channel:{channel}")
        if channel_node and channel_node.summary:
            return f"Channel: {channel}\n{channel_node.summary}"
        return ""
    
    def _get_entity_context(self, entity_ids: list[str]) -> str:
        """Get context for specific entities."""
        contexts = []
        
        for entity_id in entity_ids:
            # Get entity summary from tree
            entity_node = self.store.get_summary_node(f"entity:{entity_id}")
            if entity_node and entity_node.summary:
                contexts.append(f"{entity_node.summary}")
            else:
                # Fallback: generate from entity directly
                entity = self.store.get_entity(entity_id)
                if entity:
                    contexts.append(f"{entity.name} ({entity.entity_type})")
        
        return "\n\n".join(contexts) if contexts else ""
    
    def _get_preferences_context(self) -> str:
        """Get user preferences context."""
        prefs_node = self.store.get_summary_node("user_preferences")
        if prefs_node and prefs_node.summary:
            return prefs_node.summary
        return ""
    
    def _get_recent_context(self, event_ids: list[str]) -> str:
        """Get context from recent events."""
        events = []
        for event_id in event_ids:
            # Get event from store
            event = self.store.get_event(event_id)
            if event:
                events.append(f"- {event.content[:100]}")  # Truncate long content
        
        if events:
            return "Recent conversation:\n" + "\n".join(events)
        return ""
    
    def _get_knowledge_context(self, max_tokens: int) -> str:
        """Get general knowledge from summary tree."""
        # Get root summary
        root = self.store.get_summary_node("root")
        if root and root.summary:
            # Simple token estimation
            max_chars = max_tokens * 4
            if len(root.summary) > max_chars:
                return root.summary[:max_chars] + "..."
            return root.summary
        return ""
    
    def _format_sections(self, sections: list[tuple]) -> str:
        """Format sections into final context string."""
        parts = []
        
        for name, content, budget in sections:
            if content:
                parts.append(f"--- {name} ---")
                parts.append(content)
                parts.append("")  # Empty line between sections
        
        return "\n".join(parts).strip()
    
    def get_relevant_entities(
        self,
        query: str,
        channel: str = None,
        limit: int = 5,
    ) -> list[Entity]:
        """
        Find entities relevant to the current query.
        
        Args:
            query: Current user query
            channel: Current channel (for filtering)
            limit: Max entities to return
            
        Returns:
            List of relevant entities
        """
        # Get entities mentioned in recent events from this channel
        if channel:
            recent_entities = self.store.get_entities_for_channel(channel, limit=limit * 2)
        else:
            # Get most frequently mentioned entities
            recent_entities = self.store.get_entities_by_type("person", limit=limit * 2)
        
        # Score by recency and frequency
        scored = []
        for entity in recent_entities:
            score = entity.event_count
            if entity.last_seen:
                # Boost recently seen entities
                from datetime import datetime
                days_since = (datetime.now() - entity.last_seen).days
                if days_since < 7:
                    score *= 2  # Double score for recent mentions
            
            scored.append((entity, score))
        
        # Sort by score and return top
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:limit]]


def create_context_assembler(
    store: TurboMemoryStore,
    summary_manager: SummaryTreeManager,
    budget: Optional[ContextBudget] = None,
) -> ContextAssembler:
    """
    Factory function to create a ContextAssembler.
    
    Args:
        store: TurboMemoryStore instance
        summary_manager: SummaryTreeManager instance
        budget: Optional custom budget
        
    Returns:
        ContextAssembler instance
    """
    return ContextAssembler(store, summary_manager, budget)
