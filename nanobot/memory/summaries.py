"""Hierarchical summaries for efficient context assembly.

This module implements Phase 4 of the memory proposal:
- Summary tree management (root → channel → entity_type → entity/topic)
- Staleness tracking (refresh when >10 new events)
- Batch summarization
- Pre-computed summaries for fast context assembly
"""

from datetime import datetime
from typing import Optional

from loguru import logger

from nanobot.memory.models import SummaryNode
from nanobot.memory.store import TurboMemoryStore


class SummaryTreeManager:
    """
    Manages the hierarchical summary tree.
    
    Tree structure:
    root/
    ├── channel:telegram/
    │   ├── entity:John Smith (summary)
    │   ├── entity:Jane Doe (summary)
    │   └── topic:programming (summary)
    ├── channel:cli/
    │   └── ...
    └── user_preferences (always in context)
    """
    
    def __init__(
        self,
        store: TurboMemoryStore,
        staleness_threshold: int = 10,
        max_refresh_batch: int = 20,
    ):
        """
        Initialize the summary tree manager.
        
        Args:
            store: TurboMemoryStore for database operations
            staleness_threshold: Events before refresh (default: 10)
            max_refresh_batch: Max nodes to refresh per cycle (default: 20)
        """
        self.store = store
        self.staleness_threshold = staleness_threshold
        self.max_refresh_batch = max_refresh_batch
        
        # Ensure root node exists
        self._ensure_root_node()
        
        logger.info(f"SummaryTreeManager initialized (threshold: {staleness_threshold})")
    
    def _ensure_root_node(self):
        """Create root node if it doesn't exist."""
        root = self.store.get_summary_node("root")
        if not root:
            root = SummaryNode(
                id="root",
                node_type="root",
                key="root",
                summary="Root of conversation summary tree",
            )
            self.store.create_summary_node(root)
            logger.info("Created root summary node")
    
    def increment_staleness(self, channel: str, entity_ids: list[str] = None):
        """
        Increment staleness counter for relevant nodes after new events.
        
        Args:
            channel: Channel where events occurred
            entity_ids: List of entity IDs mentioned in events
        """
        # Get or create channel node
        channel_node = self._get_or_create_channel_node(channel)
        
        # Increment staleness
        channel_node.events_since_update += 1
        self.store.update_summary_node(channel_node)
        
        # Increment for specific entities
        if entity_ids:
            for entity_id in entity_ids:
                entity_node = self.store.get_summary_node(f"entity:{entity_id}")
                if entity_node:
                    entity_node.events_since_update += 1
                    self.store.update_summary_node(entity_node)
        
        logger.debug(f"Incremented staleness for channel {channel}")
    
    def get_stale_nodes(self, min_staleness: int = None) -> list[SummaryNode]:
        """
        Get all nodes that need refreshing.
        
        Args:
            min_staleness: Minimum staleness to consider (default: threshold)
            
        Returns:
            List of stale summary nodes
        """
        if min_staleness is None:
            min_staleness = self.staleness_threshold
        
        all_nodes = self.store.get_all_summary_nodes()
        stale_nodes = [n for n in all_nodes if n.events_since_update >= min_staleness]
        
        # Sort by staleness (highest first) and limit
        stale_nodes.sort(key=lambda n: n.events_since_update, reverse=True)
        
        return stale_nodes[:self.max_refresh_batch]
    
    def refresh_node(self, node_id: str) -> Optional[SummaryNode]:
        """
        Refresh a summary node by regenerating its content.
        
        Args:
            node_id: Node to refresh
            
        Returns:
            Updated node or None if not found
        """
        node = self.store.get_summary_node(node_id)
        if not node:
            return None
        
        try:
            # Generate new summary based on node type
            if node.node_type == "channel":
                new_summary = self._generate_channel_summary(node.key.replace("channel:", ""))
            elif node.node_type == "entity":
                entity_id = node.key.replace("entity:", "")
                new_summary = self._generate_entity_summary(entity_id)
            else:
                # Root or other types
                new_summary = self._generate_root_summary()
            
            # Update node
            node.summary = new_summary
            node.events_since_update = 0
            node.last_updated = datetime.now()
            
            self.store.update_summary_node(node)
            
            logger.info(f"Refreshed summary node: {node.key}")
            
            return node
            
        except Exception as e:
            logger.error(f"Failed to refresh node {node_id}: {e}")
            return None
    
    def refresh_all_stale(self) -> dict:
        """
        Refresh all stale nodes up to max_refresh_batch.
        
        Returns:
            Dict with refresh statistics
        """
        stale_nodes = self.get_stale_nodes()
        
        results = {
            "total_stale": len(stale_nodes),
            "refreshed": 0,
            "failed": 0,
            "nodes": [],
        }
        
        for node in stale_nodes:
            refreshed = self.refresh_node(node.id)
            if refreshed:
                results["refreshed"] += 1
                results["nodes"].append({
                    "id": node.id,
                    "key": node.key,
                    "type": node.node_type,
                })
            else:
                results["failed"] += 1
        
        logger.info(f"Summary refresh complete: {results['refreshed']} refreshed, {results['failed']} failed")
        
        return results
    
    def _get_or_create_channel_node(self, channel: str) -> SummaryNode:
        """Get or create a channel summary node."""
        node_key = f"channel:{channel}"
        node = self.store.get_summary_node(node_key)
        
        if not node:
            node = SummaryNode(
                id=node_key,
                node_type="channel",
                key=node_key,
                parent_id="root",
                summary=f"Summary for {channel} conversations",
            )
            self.store.create_summary_node(node)
            logger.info(f"Created channel summary node: {channel}")
        
        return node
    
    def _generate_channel_summary(self, channel: str) -> str:
        """Generate summary for a channel."""
        # Get recent events for this channel
        events = self.store.get_events_for_channel(channel, limit=50)
        
        if not events:
            return f"No recent activity in {channel}."
        
        # Get entity counts
        entities = self.store.get_entities_for_channel(channel, limit=20)
        
        summary_parts = [
            f"Channel: {channel}",
            f"Recent events: {len(events)}",
            f"Active entities: {len(entities)}",
        ]
        
        # Add entity list
        if entities:
            entity_names = [e.name for e in entities[:5]]
            summary_parts.append(f"Key topics: {', '.join(entity_names)}")
        
        return "\n".join(summary_parts)
    
    def _generate_entity_summary(self, entity_id: str) -> str:
        """Generate summary for an entity."""
        entity = self.store.get_entity(entity_id)
        if not entity:
            return "Entity not found."
        
        # Get facts about this entity
        facts = self.store.get_facts_for_entity(entity_id)
        
        summary_parts = [
            f"Entity: {entity.name}",
            f"Type: {entity.entity_type}",
            f"Mentions: {entity.event_count}",
        ]
        
        # Add facts
        if facts:
            fact_texts = [f"{f.predicate}: {f.object_text}" for f in facts[:3]]
            summary_parts.append(f"Known facts: {'; '.join(fact_texts)}")
        
        # Add aliases
        if entity.aliases:
            summary_parts.append(f"Also known as: {', '.join(entity.aliases[:3])}")
        
        return "\n".join(summary_parts)
    
    def _generate_root_summary(self) -> str:
        """Generate root summary of all conversations."""
        stats = self.store.get_stats()
        
        return (
            f"Total events: {stats.get('events', 0)}\n"
            f"Total entities: {stats.get('entities', 0)}\n"
            f"Total facts: {stats.get('facts', 0)}\n"
            f"Summary nodes: {stats.get('summary_nodes', 0)}"
        )
    
    def get_summary_for_context(
        self,
        channel: str = None,
        entity_ids: list[str] = None,
        max_tokens: int = 1000,
    ) -> str:
        """
        Get pre-computed summaries for context assembly.
        
        Args:
            channel: Current channel (optional)
            entity_ids: Entity IDs to include (optional)
            max_tokens: Maximum tokens to return
            
        Returns:
            Combined summary text
        """
        summaries = []
        
        # Get channel summary
        if channel:
            channel_node = self.store.get_summary_node(f"channel:{channel}")
            if channel_node and channel_node.summary:
                summaries.append(f"## Channel: {channel}\n{channel_node.summary}")
        
        # Get entity summaries
        if entity_ids:
            for entity_id in entity_ids[:5]:  # Limit to top 5
                entity_node = self.store.get_summary_node(f"entity:{entity_id}")
                if entity_node and entity_node.summary:
                    summaries.append(f"## {entity_node.key.replace('entity:', '')}\n{entity_node.summary}")
        
        # Get user preferences (always include)
        prefs_node = self.store.get_summary_node("user_preferences")
        if prefs_node and prefs_node.summary:
            summaries.append(f"## Preferences\n{prefs_node.summary}")
        
        # Combine and truncate
        combined = "\n\n".join(summaries)
        
        # Simple token estimation (4 chars ≈ 1 token)
        if len(combined) > max_tokens * 4:
            combined = combined[:max_tokens * 4] + "\n...[truncated]"
        
        return combined


def create_summary_manager(store: TurboMemoryStore, **kwargs) -> SummaryTreeManager:
    """Factory function to create a SummaryTreeManager."""
    return SummaryTreeManager(store, **kwargs)
