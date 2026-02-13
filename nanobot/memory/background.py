"""Background processing for the memory system.

This module provides the ActivityTracker and BackgroundProcessor classes
for activity-aware background task execution.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger


class ActivityTracker:
    """
    Tracks user chat activity to determine when it's safe to run background tasks.
    
    Prevents background processing from interfering with active conversations.
    """
    
    def __init__(self, quiet_threshold_seconds: int = 30):
        """
        Initialize the activity tracker.
        
        Args:
            quiet_threshold_seconds: Seconds of inactivity before user is considered "quiet"
        """
        self.quiet_threshold = timedelta(seconds=quiet_threshold_seconds)
        self.last_activity: Optional[datetime] = None
        
        logger.debug(f"ActivityTracker initialized (threshold: {quiet_threshold_seconds}s)")
    
    def mark_activity(self):
        """Call when user sends a message."""
        self.last_activity = datetime.now()
        logger.debug("User activity marked")
    
    def is_user_active(self) -> bool:
        """
        Check if user has been active in the last N seconds.
        
        Returns:
            True if user was active within quiet_threshold_seconds
        """
        if self.last_activity is None:
            return False
        
        time_since = datetime.now() - self.last_activity
        return time_since < self.quiet_threshold
    
    def seconds_since_last_activity(self) -> float:
        """
        Get seconds since last user message.
        
        Returns:
            Seconds since last activity, or infinity if no activity
        """
        if self.last_activity is None:
            return float('inf')
        
        return (datetime.now() - self.last_activity).total_seconds()


class BackgroundProcessor:
    """
    Minimal background processor for single-user deployment.
    
    Runs one task at a time every N seconds when user is inactive.
    No complex WorkerPool or TaskQueue - simple and reliable.
    """
    
    def __init__(
        self,
        memory_store,
        activity_tracker: ActivityTracker,
        interval_seconds: int = 60,
    ):
        """
        Initialize the background processor.
        
        Args:
            memory_store: MemoryStore instance for database operations
            activity_tracker: ActivityTracker for user activity monitoring
            interval_seconds: Seconds between processing cycles
        """
        self.memory_store = memory_store
        self.activity_tracker = activity_tracker
        self.interval_seconds = interval_seconds
        
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        logger.info(f"BackgroundProcessor initialized (interval: {interval_seconds}s)")
    
    async def start(self):
        """Start the background processing loop."""
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background processor started")
    
    async def stop(self):
        """Stop the background processor gracefully."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background processor stopped")
    
    async def _loop(self):
        """Main processing loop."""
        while self.running:
            await asyncio.sleep(self.interval_seconds)
            
            # Skip if user is actively chatting
            if self.activity_tracker.is_user_active():
                logger.debug("User is active, skipping background processing")
                continue
            
            try:
                await self._process_cycle()
            except Exception as e:
                logger.error(f"Background processing error: {e}")
                # Log and continue - will retry next cycle
    
    async def _process_cycle(self):
        """
        Process one cycle of background tasks.
        
        Current tasks:
        1. Extract entities from pending events
        2. Refresh stale summaries (every 5 cycles)
        3. Apply learning decay (every 60 cycles ~ 1 hour)
        """
        # Track which tasks ran
        tasks_ran = []
        
        # Task 1: Extract entities from pending events
        pending = await self._extract_pending_events()
        if pending > 0:
            tasks_ran.append(f"extracted {pending} events")
        
        # Task 2: Refresh stale summaries (every 5th cycle = every 5 min)
        # Use time-based check instead of cycle counter
        import time
        if int(time.time()) % 300 < self.interval_seconds:
            refreshed = await self._refresh_summaries()
            if refreshed > 0:
                tasks_ran.append(f"refreshed {refreshed} summaries")
        
        # Task 3: Apply learning decay (every hour)
        if int(time.time()) % 3600 < self.interval_seconds:
            decayed = await self._decay_learnings()
            if decayed > 0:
                tasks_ran.append(f"decayed {decayed} learnings")
        
        if tasks_ran:
            logger.info(f"Background tasks: {', '.join(tasks_ran)}")
    
    async def _extract_pending_events(self) -> int:
        """
        Extract entities from pending events.
        
        Returns:
            Number of events processed
        """
        from nanobot.memory.extraction import extract_entities, ExtractionConfig
        from nanobot.config.schema import MemoryConfig
        
        # Get pending events
        pending = self.memory_store.get_pending_events(limit=20)
        if not pending:
            return 0
        
        # Get extraction config from memory store config
        # Use default config (gliner2) if not available
        config = ExtractionConfig(provider="gliner2")  # Use GLiNER2 as primary extractor
        
        count = 0
        for event in pending:
            try:
                # Extract entities, edges, and facts
                result = await extract_entities(event, config)
                
                # Save entities
                for entity in result.entities:
                    # Check for existing entity
                    existing = self.memory_store.find_entity_by_name(entity.name)
                    if existing:
                        # Merge with existing
                        existing.aliases = list(set(existing.aliases + entity.aliases))
                        existing.source_event_ids = list(set(existing.source_event_ids + entity.source_event_ids))
                        existing.event_count += 1
                        existing.last_seen = entity.last_seen
                        self.memory_store.update_entity(existing)
                    else:
                        self.memory_store.save_entity(entity)
                
                # TODO: Save edges and facts (implement in Phase 3.6)
                
                # Mark as extracted
                self.memory_store.mark_event_extracted(event.id, "complete")
                count += 1
                
            except Exception as e:
                logger.error(f"Failed to extract entities from event {event.id}: {e}")
                self.memory_store.mark_event_extracted(event.id, "failed")
        
        return count
    
    async def _refresh_summaries(self) -> int:
        """
        Refresh stale summary nodes (Phase 4 & 6).
        
        Returns:
            Number of summaries refreshed
        """
        from nanobot.memory.summaries import SummaryTreeManager
        
        try:
            # Create temporary summary manager
            summary_manager = SummaryTreeManager(
                store=self.memory_store,
                staleness_threshold=10,
                max_refresh_batch=20,
            )
            
            # Refresh stale summaries
            stats = summary_manager.refresh_all_stale()
            
            if stats["refreshed"] > 0:
                logger.info(f"Summaries refreshed: {stats['refreshed']} nodes")
            
            return stats["refreshed"]
            
        except Exception as e:
            logger.error(f"Failed to refresh summaries: {e}")
            return 0
    
    async def _decay_learnings(self) -> int:
        """
        Apply decay to learning relevance scores (Phase 6).
        
        Returns:
            Number of learnings decayed
        """
        from nanobot.memory.learning import LearningManager
        
        try:
            # Create temporary learning manager
            learning_manager = LearningManager(
                store=self.memory_store,
                decay_days=14,
                decay_rate=0.05,
            )
            
            # Apply decay
            stats = learning_manager.apply_decay()
            
            if stats["decayed"] > 0 or stats["removed"] > 0:
                logger.info(f"Learning decay applied: {stats['decayed']} decayed, {stats['removed']} removed")
            
            return stats["decayed"] + stats["removed"]
            
        except Exception as e:
            logger.error(f"Failed to apply learning decay: {e}")
            return 0


# Placeholder extraction function (will be implemented in extractors module)
async def extract_entities(event):
    """
    Extract entities from an event.
    
    This is a placeholder that will be replaced with actual
    GLiNER2/spaCy extraction in Phase 3.3.
    
    Args:
        event: Event to extract from
        
    Returns:
        List of Entity objects
    """
    # TODO: Implement actual extraction
    return []
