"""User preferences aggregation and management.

This module aggregates learnings into a user_preferences summary node
that can be included in every context for personalization.
"""

from datetime import datetime
from typing import Optional

from loguru import logger

from nanobot.memory.models import Learning, SummaryNode
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.summaries import SummaryTreeManager


class PreferencesAggregator:
    """
    Aggregates learnings into user preferences summary.
    
    Collects all active learnings and compiles them into a
    readable summary for the user_preferences node.
    """
    
    def __init__(
        self,
        store: TurboMemoryStore,
        summary_manager: SummaryTreeManager,
    ):
        """
        Initialize preferences aggregator.
        
        Args:
            store: TurboMemoryStore for persistence
            summary_manager: SummaryTreeManager for summary nodes
        """
        self.store = store
        self.summary_manager = summary_manager
        
        # Ensure user_preferences node exists
        self._ensure_preferences_node()
        
        logger.info("PreferencesAggregator initialized")
    
    def _ensure_preferences_node(self):
        """Create user_preferences summary node if it doesn't exist."""
        node = self.store.get_summary_node("user_preferences")
        if not node:
            node = SummaryNode(
                id="user_preferences",
                node_type="user_preferences",
                key="user_preferences",
                parent_id="root",
                summary="No preferences learned yet.",
                events_since_update=0,
            )
            self.store.create_summary_node(node)
            logger.info("Created user_preferences summary node")
    
    async def aggregate_preferences(self) -> SummaryNode:
        """
        Aggregate all learnings into user_preferences summary.
        
        Returns:
            Updated user_preferences node
        """
        # Get all active learnings
        learnings = self.store.get_all_learnings(active_only=True)
        
        if not learnings:
            # No learnings yet
            return self._update_preferences_summary("No preferences learned yet.")
        
        # Categorize learnings
        categorized = self._categorize_learnings(learnings)
        
        # Build summary
        summary_parts = []
        summary_parts.append(f"## User Preferences ({len(learnings)} learned)")
        summary_parts.append("")
        
        # Add high-confidence preferences
        high_conf = [l for l in learnings if l.confidence >= 0.8]
        if high_conf:
            summary_parts.append("### Confirmed Preferences")
            for learning in high_conf[:5]:  # Top 5
                summary_parts.append(f"• {learning.content}")
            summary_parts.append("")
        
        # Add by category
        for category, items in categorized.items():
            if items:
                summary_parts.append(f"### {category.replace('_', ' ').title()}")
                for learning in items[:3]:  # Top 3 per category
                    summary_parts.append(f"• {learning.content}")
                summary_parts.append("")
        
        # Add recommendations
        recommendations = [l.recommendation for l in learnings if l.recommendation]
        if recommendations:
            summary_parts.append("### Key Recommendations")
            for rec in recommendations[:5]:
                summary_parts.append(f"• {rec}")
            summary_parts.append("")
        
        # Add tool-specific preferences
        tool_prefs = [l for l in learnings if l.tool_name]
        if tool_prefs:
            summary_parts.append("### Tool Preferences")
            for learning in tool_prefs:
                summary_parts.append(f"• {learning.tool_name}: {learning.content}")
            summary_parts.append("")
        
        # Join into final summary
        summary = "\n".join(summary_parts)
        
        # Update node
        return self._update_preferences_summary(summary)
    
    def _categorize_learnings(self, learnings: list[Learning]) -> dict:
        """Categorize learnings by type/topic."""
        categories = {
            "communication": [],
            "formatting": [],
            "tools": [],
            "workflow": [],
            "other": [],
        }
        
        keywords = {
            "communication": ["email", "message", "response", "reply", "communication", "write", "tone", "style"],
            "formatting": ["format", "markdown", "code", "syntax", "style", "layout", "indent"],
            "tools": ["tool", "command", "script", "function", "search", "file"],
            "workflow": ["workflow", "process", "step", "organize", "structure", "schedule"],
        }
        
        for learning in learnings:
            content_lower = learning.content.lower()
            categorized = False
            
            for category, words in keywords.items():
                if any(word in content_lower for word in words):
                    categories[category].append(learning)
                    categorized = True
                    break
            
            if not categorized:
                categories["other"].append(learning)
        
        return categories
    
    def _update_preferences_summary(self, summary: str) -> SummaryNode:
        """Update the user_preferences summary node."""
        node = self.store.get_summary_node("user_preferences")
        if not node:
            # Shouldn't happen (created in init), but handle gracefully
            self._ensure_preferences_node()
            node = self.store.get_summary_node("user_preferences")
        
        node.summary = summary
        node.last_updated = datetime.now()
        node.events_since_update = 0
        
        self.store.update_summary_node(node)
        
        logger.info("Updated user_preferences summary")
        return node
    
    def get_preferences_summary(self) -> str:
        """
        Get current preferences summary text.
        
        Returns:
            Summary text or default message
        """
        node = self.store.get_summary_node("user_preferences")
        if node and node.summary:
            return node.summary
        return "No preferences learned yet."
    
    async def refresh_if_needed(self, staleness_threshold: int = 10) -> bool:
        """
        Refresh preferences if stale (lots of new learnings).
        
        Args:
            staleness_threshold: How many new learnings before refresh
            
        Returns:
            True if refreshed, False otherwise
        """
        node = self.store.get_summary_node("user_preferences")
        if not node:
            return False
        
        if node.events_since_update >= staleness_threshold:
            await self.aggregate_preferences()
            return True
        
        return False
    
    def increment_staleness(self):
        """Increment staleness counter (call when new learning created)."""
        node = self.store.get_summary_node("user_preferences")
        if node:
            node.events_since_update += 1
            self.store.update_summary_node(node)
    
    def get_preference_count(self) -> int:
        """Get total number of active preferences/learnings."""
        learnings = self.store.get_all_learnings(active_only=True)
        return len(learnings)
    
    def get_high_confidence_preferences(self, min_confidence: float = 0.8) -> list[Learning]:
        """
        Get only high-confidence preferences.
        
        Args:
            min_confidence: Minimum confidence threshold
            
        Returns:
            List of high-confidence learnings
        """
        learnings = self.store.get_all_learnings(active_only=True)
        return [l for l in learnings if l.confidence >= min_confidence]


def create_preferences_aggregator(
    store: TurboMemoryStore,
    summary_manager: SummaryTreeManager,
) -> PreferencesAggregator:
    """Factory function to create PreferencesAggregator."""
    return PreferencesAggregator(store, summary_manager)
