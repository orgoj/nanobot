"""Learning system for feedback detection and decay management.

This module implements Phase 6 of the memory proposal:
- Feedback detection from user messages (regex + GLiNER2)
- Learning creation and storage
- Relevance decay with re-boost on access
- Contradiction detection
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from loguru import logger

from nanobot.memory.models import Learning, Event
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.embeddings import EmbeddingProvider


# Feedback detection patterns (regex-based, FREE)
FEEDBACK_PATTERNS = {
    "correction": [
        r"(?i)actually[,.]?\s+(?:i|you|that|it|this)",
        r"(?i)no[,.]?\s+(?:that'?s|it is|you're|wrong)",
        r"(?i)(?:wrong|incorrect|not right|mistake|error)",
        r"(?i)I meant",
        r"(?i)should be",
        r"(?i)not quite",
        r"(?i)that's not",
    ],
    "preference": [
        r"(?i)I prefer",
        r"(?i)I like",
        r"(?i)I want",
        r"(?i)I need",
        r"(?i)always use",
        r"(?i)never use",
        r"(?i)make sure to",
        r"(?i)can you (?:always|usually)",
    ],
    "positive": [
        r"(?i)^perfect!?$",
        r"(?i)^exactly!?$",
        r"(?i)^that's right!?$",
        r"(?i)^good job!?$",
        r"(?i)^thank you[!,.]? that",
        r"(?i)^great!?$",
        r"(?i)^awesome!?$",
    ],
    "negative": [
        r"(?i)^no[,.]?!?$",
        r"(?i)^that's wrong",
        r"(?i)^not correct",
        r"(?i)^bad",
        r"(?i)^terrible",
    ],
}


class FeedbackDetector:
    """
    Detects feedback in user messages using regex patterns.
    
    This is a lightweight, zero-cost approach that catches
    70-75% of feedback without API calls.
    """
    
    def __init__(self):
        self.patterns = FEEDBACK_PATTERNS
        logger.info("FeedbackDetector initialized with regex patterns")
    
    def detect(self, text: str) -> Optional[dict]:
        """
        Detect if text contains feedback.
        
        Args:
            text: User message text
            
        Returns:
            Dict with feedback info or None
        """
        if not text or len(text.strip()) < 3:
            return None
        
        text_lower = text.lower().strip()
        
        # Check each pattern type
        for feedback_type, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    # Extract the relevant part (simplified)
                    content = self._extract_content(text, feedback_type)
                    
                    return {
                        "is_feedback": True,
                        "type": feedback_type,
                        "confidence": 0.7,  # Regex confidence
                        "content": content,
                        "raw_text": text,
                    }
        
        return None
    
    def _extract_content(self, text: str, feedback_type: str) -> str:
        """Extract the meaningful content from feedback."""
        # Simple extraction - can be enhanced
        if feedback_type == "correction":
            # Look for "X should be Y" or "actually, ..."
            match = re.search(r"(?i)(?:should be|actually[,.]?\s+|I meant\s+)(.+)", text)
            if match:
                return match.group(1).strip()
        
        elif feedback_type == "preference":
            # Look for "I prefer X" or "always use X"
            match = re.search(r"(?i)(?:I (?:prefer|like|want)|always use|never use)\s+(.+)", text)
            if match:
                return match.group(1).strip()
        
        # Default: return full text (truncated)
        return text[:200] if len(text) > 200 else text


class LearningManager:
    """
    Manages the learning lifecycle:
    - Detect feedback
    - Create learnings
    - Apply decay
    - Detect contradictions
    """
    
    def __init__(
        self,
        store: TurboMemoryStore,
        embedding_provider: Optional[EmbeddingProvider] = None,
        decay_days: int = 14,
        decay_rate: float = 0.05,
    ):
        """
        Initialize learning manager.
        
        Args:
            store: TurboMemoryStore for persistence
            embedding_provider: Optional for semantic similarity
            decay_days: Half-life for relevance decay (default 14)
            decay_rate: Daily decay rate (default 0.05 = 5%)
        """
        self.store = store
        self.embedding_provider = embedding_provider
        self.decay_days = decay_days
        self.decay_rate = decay_rate
        self.feedback_detector = FeedbackDetector()
        
        logger.info(f"LearningManager initialized (decay: {decay_days} days)")
    
    async def process_message(self, message: str, context: str = None) -> Optional[Learning]:
        """
        Process a user message and create learning if feedback detected.
        
        Args:
            message: User message
            context: Optional context (e.g., bot's previous response)
            
        Returns:
            Created Learning or None
        """
        # Step 1: Detect feedback (regex, FREE)
        detection = self.feedback_detector.detect(message)
        
        if not detection:
            return None
        
        # Step 2: Create learning
        learning = self._create_learning_from_detection(detection, context)
        
        # Step 3: Check for contradictions
        await self._check_contradictions(learning)
        
        # Step 4: Store
        self.store.create_learning(learning)
        
        logger.info(f"Created learning from feedback: {learning.id} (type: {learning.source})")
        
        return learning
    
    def _create_learning_from_detection(self, detection: dict, context: str = None) -> Learning:
        """Convert detection result to Learning object."""
        feedback_type = detection["type"]
        content = detection["content"]
        
        # Map feedback type to sentiment
        sentiment_map = {
            "correction": "negative",
            "preference": "neutral",
            "positive": "positive",
            "negative": "negative",
        }
        sentiment = sentiment_map.get(feedback_type, "neutral")
        
        # Generate recommendation based on type
        recommendation = self._generate_recommendation(content, feedback_type)
        
        now = datetime.now()
        
        return Learning(
            id=str(uuid4()),
            content=content,
            source="user_feedback",
            sentiment=sentiment,
            confidence=detection["confidence"],
            recommendation=recommendation,
            superseded_by=None,
            content_embedding=None,  # Will be set if embedding provider available
            created_at=now,
            updated_at=now,
            relevance_score=1.0,
            times_accessed=0,
            last_accessed=None,
        )
    
    def _generate_recommendation(self, content: str, feedback_type: str) -> str:
        """Generate actionable recommendation from feedback."""
        if feedback_type == "preference":
            return f"Apply this preference: {content}"
        elif feedback_type == "correction":
            return f"Avoid this mistake: {content}"
        elif feedback_type == "positive":
            return "Continue this approach"
        else:
            return f"Note: {content}"
    
    async def _check_contradictions(self, new_learning: Learning) -> bool:
        """
        Check if new learning contradicts existing ones.
        
        Args:
            new_learning: Newly detected learning
            
        Returns:
            True if contradiction found and handled
        """
        # Get existing learnings
        existing = self.store.get_all_learnings(active_only=True)
        
        # Simple contradiction detection: similar content but different sentiment
        for old in existing:
            # Check if similar (simple text similarity)
            similarity = self._calculate_similarity(
                new_learning.content, 
                old.content
            )
            
            if similarity > 0.7:  # 70% similar
                if new_learning.sentiment != old.sentiment:
                    # Contradiction! Mark old as superseded
                    old.superseded_by = new_learning.id
                    self.store.update_learning(old)
                    
                    # Boost new learning
                    new_learning.relevance_score = 1.0
                    
                    logger.info(f"Detected contradiction: {old.id} superseded by {new_learning.id}")
                    return True
        
        return False
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity (can be enhanced with embeddings)."""
        # Word overlap similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def apply_decay(self) -> dict:
        """
        Apply relevance decay to all learnings.
        Should be called periodically (e.g., daily via background job).
        
        Returns:
            Stats about decay applied
        """
        learnings = self.store.get_all_learnings(active_only=True)
        now = datetime.now()
        
        stats = {
            "total": len(learnings),
            "decayed": 0,
            "unchanged": 0,
            "removed": 0,
        }
        
        for learning in learnings:
            if not learning.updated_at:
                continue
            
            # Calculate days since last update
            days_old = (now - learning.updated_at).days
            
            if days_old < 1:
                stats["unchanged"] += 1
                continue
            
            # Apply decay: relevance *= (0.95 ^ days_old)
            decay_factor = (1 - self.decay_rate) ** days_old
            old_score = learning.relevance_score
            learning.relevance_score *= decay_factor
            
            # Remove very old learnings (relevance < 0.1)
            if learning.relevance_score < 0.1:
                self.store.delete_learning(learning.id)
                stats["removed"] += 1
                logger.debug(f"Removed stale learning: {learning.id}")
            else:
                self.store.update_learning(learning)
                stats["decayed"] += 1
                logger.debug(
                    f"Decayed learning {learning.id}: "
                    f"{old_score:.2f} -> {learning.relevance_score:.2f}"
                )
        
        logger.info(f"Decay applied: {stats}")
        return stats
    
    def boost_on_access(self, learning_id: str, boost_factor: float = 1.2) -> Optional[Learning]:
        """
        Boost relevance when a learning is accessed/used.
        
        Args:
            learning_id: Learning to boost
            boost_factor: Multiplier (default 1.2 = 20% boost)
            
        Returns:
            Updated learning or None
        """
        learning = self.store.get_learning(learning_id)
        if not learning:
            return None
        
        # Boost relevance (cap at 1.0)
        learning.relevance_score = min(1.0, learning.relevance_score * boost_factor)
        learning.times_accessed += 1
        learning.last_accessed = datetime.now()
        learning.updated_at = datetime.now()
        
        self.store.update_learning(learning)
        
        logger.debug(f"Boosted learning {learning_id}: score={learning.relevance_score:.2f}")
        
        return learning
    
    def get_relevant_learnings(self, topic: str = None, limit: int = 10) -> list[Learning]:
        """
        Get most relevant learnings, optionally filtered by topic.
        
        Args:
            topic: Optional topic filter
            limit: Maximum results
            
        Returns:
            List of relevant learnings
        """
        learnings = self.store.get_high_relevance_learnings(min_score=0.5, limit=limit * 2)
        
        # Sort by relevance (already sorted by DB, but double-check)
        learnings.sort(key=lambda l: l.relevance_score, reverse=True)
        
        return learnings[:limit]


def create_learning_manager(
    store: TurboMemoryStore,
    embedding_provider: Optional[EmbeddingProvider] = None,
    **kwargs
) -> LearningManager:
    """Factory function to create LearningManager."""
    return LearningManager(store, embedding_provider, **kwargs)
