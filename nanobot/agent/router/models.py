"""Data models for the smart router."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RoutingTier(str, Enum):
    """Capability tiers for model selection."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    REASONING = "reasoning"
    CODING = "coding"


@dataclass
class RoutingDecision:
    """Result of a routing classification."""
    
    tier: RoutingTier
    model: str
    confidence: float
    layer: str  # "client" or "llm"
    reasoning: str
    estimated_tokens: int
    needs_tools: bool
    
    # Metadata for analytics
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass  
class ClassificationScores:
    """Scores from the 14-dimension classification system."""
    
    reasoning_markers: float = 0.0
    code_presence: float = 0.0
    simple_indicators: float = 0.0
    multi_step_patterns: float = 0.0
    technical_terms: float = 0.0
    token_count: float = 0.0
    creative_markers: float = 0.0
    question_complexity: float = 0.0
    constraint_count: float = 0.0
    imperative_verbs: float = 0.0
    output_format: float = 0.0
    domain_specificity: float = 0.0
    reference_complexity: float = 0.0
    negation_complexity: float = 0.0
    social_interaction: float = 0.0
    
    def calculate_weighted_sum(self, weights: dict[str, float]) -> float:
        """Calculate weighted sum of all scores."""
        total = 0.0
        for field_name, weight in weights.items():
            if hasattr(self, field_name):
                total += getattr(self, field_name) * weight
        return total
    
    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "reasoning_markers": self.reasoning_markers,
            "code_presence": self.code_presence,
            "simple_indicators": self.simple_indicators,
            "multi_step_patterns": self.multi_step_patterns,
            "technical_terms": self.technical_terms,
            "token_count": self.token_count,
            "creative_markers": self.creative_markers,
            "question_complexity": self.question_complexity,
            "constraint_count": self.constraint_count,
            "imperative_verbs": self.imperative_verbs,
            "output_format": self.output_format,
            "domain_specificity": self.domain_specificity,
            "reference_complexity": self.reference_complexity,
            "negation_complexity": self.negation_complexity,
            "social_interaction": self.social_interaction,
        }


@dataclass
class RoutingPattern:
    """A learned pattern for client-side classification."""
    
    regex: str
    tier: RoutingTier
    confidence: float
    examples: list[str]
    added_at: str
    
    # NEW: Performance tracking fields
    times_used: int = 0
    times_matched: int = 0
    times_correct: int = 0
    last_used: Optional[str] = None
    source: str = "manual"  # "manual", "auto_calibration", "user_added"
    action_context: Optional[str] = None  # "write", "explain", "analyze", etc.
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate of this pattern."""
        if self.times_matched == 0:
            return 0.0
        return self.times_correct / self.times_matched
    
    @property
    def is_effective(self) -> bool:
        """
        Check if pattern is effective based on multiple factors.
        
        A pattern is effective if:
        - It's new (less than 7 days old) - grace period
        - It has good success rate (>= 40%)
        - It's used frequently with decent success
        """
        # Check if new (grace period)
        try:
            added = datetime.fromisoformat(self.added_at)
            age_days = (datetime.now() - added).days
            if age_days < 7:
                return True  # New patterns get a chance
        except:
            pass
        
        # Check success rate
        if self.times_matched >= 5:
            return self.success_rate >= 0.4  # 40% success minimum
        
        # Not enough data to judge, assume effective
        return True
    
    @property
    def effectiveness_score(self) -> float:
        """
        Calculate overall effectiveness score (0-100).
        
        Considers:
        - Success rate (0-50 points)
        - Usage frequency (0-30 points)
        - Recency (0-20 points)
        """
        score = 0.0
        
        # Success rate contribution (0-50 points)
        score += self.success_rate * 50
        
        # Usage frequency (0-30 points)
        if self.times_used > 100:
            score += 30
        elif self.times_used > 50:
            score += 20
        elif self.times_used > 10:
            score += 10
        
        # Recency (0-20 points)
        if self.last_used:
            try:
                last = datetime.fromisoformat(self.last_used)
                days_since = (datetime.now() - last).days
                if days_since < 7:
                    score += 20
                elif days_since < 30:
                    score += 10
                elif days_since < 90:
                    score += 5
            except:
                pass
        
        return score
    
    def record_usage(self, was_matched: bool = False, was_correct: bool = False) -> None:
        """Record pattern usage for analytics."""
        self.times_used += 1
        self.last_used = datetime.now().isoformat()
        
        if was_matched:
            self.times_matched += 1
            if was_correct:
                self.times_correct += 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "regex": self.regex,
            "tier": self.tier.value,
            "confidence": self.confidence,
            "examples": self.examples,
            "added_at": self.added_at,
            "times_used": self.times_used,
            "times_matched": self.times_matched,
            "times_correct": self.times_correct,
            "last_used": self.last_used,
            "source": self.source,
            "action_context": self.action_context,
            "success_rate": self.success_rate,
            "is_effective": self.is_effective,
            "effectiveness_score": self.effectiveness_score,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RoutingPattern":
        """Create from dictionary."""
        return cls(
            regex=data["regex"],
            tier=RoutingTier(data["tier"]),
            confidence=data["confidence"],
            examples=data.get("examples", []),
            added_at=data["added_at"],
            times_used=data.get("times_used", 0),
            times_matched=data.get("times_matched", 0),
            times_correct=data.get("times_correct", 0),
            last_used=data.get("last_used"),
            source=data.get("source", "manual"),
            action_context=data.get("action_context"),
        )
