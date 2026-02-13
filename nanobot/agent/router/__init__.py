"""
Smart Router package for intelligent LLM model selection.

Provides two-layer classification:
1. Client-side pattern matching (fast)
2. LLM-assisted classification (fallback for uncertain cases)

With sticky routing, feedback learning, and auto-calibration.
"""

from .calibration import CalibrationManager
from .classifier import ClientSideClassifier, classify_content
from .llm_router import LLMRouter
from .models import RoutingDecision, RoutingTier
from .sticky import StickyRouter

__all__ = [
    "ClientSideClassifier",
    "classify_content",
    "LLMRouter",
    "StickyRouter",
    "CalibrationManager",
    "RoutingDecision",
    "RoutingTier",
]
