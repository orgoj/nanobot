"""Sticky routing with per-message override capability."""

from typing import Optional

from nanobot.session.manager import Session

from .classifier import ClientSideClassifier
from .llm_router import LLMRouter
from .models import ClassificationScores, RoutingDecision, RoutingTier


class StickyRouter:
    """
    Router with sticky routing - maintains tier across conversation
    but allows downgrade when message is explicitly simple.
    """
    
    def __init__(
        self,
        client_classifier: ClientSideClassifier,
        llm_router: Optional[LLMRouter] = None,
        context_window: int = 5,
        downgrade_confidence: float = 0.9,
    ):
        self.client_classifier = client_classifier
        self.llm_router = llm_router
        self.context_window = context_window
        self.downgrade_confidence = downgrade_confidence
    
    async def classify(
        self,
        content: str,
        session: Session,
    ) -> RoutingDecision:
        """
        Classify with sticky routing logic.
        
        Sticky behavior: If recent messages were complex, stay complex
        unless current message is explicitly simple.
        """
        # Layer 1: Client-side classification
        client_decision, scores = self.client_classifier.classify(content)
        
        # Check if we should use client-side result
        if client_decision.confidence >= self.client_classifier.min_confidence:
            # Check sticky routing context
            return self._apply_sticky_logic(
                content, session, client_decision, scores, layer="client"
            )
        
        # Layer 2: LLM-assisted fallback (if available)
        if self.llm_router:
            # Build context from Layer 1 for Layer 2
            from .llm_router import ClassificationContext
            
            context = ClassificationContext(
                action_type=client_decision.metadata.get("action_type", "general"),
                has_negations=len(client_decision.metadata.get("negations", [])) > 0,
                negation_details=client_decision.metadata.get("negations", []),
                has_code_blocks=scores.code_presence > 0.7,
                question_type=client_decision.metadata.get("question_type"),
            )
            
            # Pass context to LLM router
            llm_decision = await self.llm_router.classify(content, context=context)
            
            # Learn: Record comparison for feedback loop
            self._record_feedback(content, client_decision, llm_decision)
            
            return self._apply_sticky_logic(
                content, session, llm_decision, scores, layer="llm"
            )
        
        # No LLM fallback - use client decision even if low confidence
        return self._apply_sticky_logic(
            content, session, client_decision, scores, layer="client"
        )
    
    def _apply_sticky_logic(
        self,
        content: str,
        session: Session,
        decision: RoutingDecision,
        scores: ClassificationScores,
        layer: str,
    ) -> RoutingDecision:
        """
        Apply sticky routing logic.
        
        Rules:
        1. If message is OBVIOUSLY simple (≥0.95 confidence), always use SIMPLE
        2. If no recent complex messages, use current decision
        3. If recent messages were complex, check if we should downgrade
        4. Downgrade only if current message is explicitly simple with high confidence
        """
        # EXCEPTION: Unambiguous simple messages should ALWAYS use SIMPLE tier
        # regardless of conversation context (cost optimization)
        # Examples: "thanks" (0.90), "good morning" (0.95), "test message" (0.95)
        # These never need expensive models - saves 90% cost vs keeping COMPLEX
        # IMPORTANT: Don't update session metadata - these are "interruptions" that
        # shouldn't reset the conversation tier for follow-up messages
        if decision.tier == RoutingTier.SIMPLE and decision.confidence >= 0.90:
            # Keep the original tier in metadata for context continuity
            # but force this message to use SIMPLE
            decision.metadata["sticky_override"] = "always_simple"
            decision.metadata["session_tier_preserved"] = session.metadata.get("routing_tier", "unknown")
            return decision
        
        # Get recent conversation context
        recent_tiers = self._get_recent_tiers(session)
        
        # Check if conversation has been complex recently
        has_recent_complex = any(
            tier in [RoutingTier.COMPLEX, RoutingTier.REASONING]
            for tier in recent_tiers
        )
        
        if not has_recent_complex:
            # No recent complexity - use current decision
            session.metadata["routing_tier"] = decision.tier.value
            return decision
        
        # Recent complexity exists - check for explicit downgrade
        if decision.tier == RoutingTier.SIMPLE:
            # Current message is simple - check if downgrade is allowed
            if self._should_downgrade(content, scores):
                # Allow downgrade
                session.metadata["routing_tier"] = RoutingTier.SIMPLE.value
                decision.metadata["sticky_override"] = "downgrade_allowed"
                return decision
        
        # Stay at complex tier
        current_tier = session.metadata.get("routing_tier", "medium")
        if current_tier in ["complex", "reasoning"]:
            decision.tier = RoutingTier(current_tier)
            decision.metadata["sticky_maintained"] = True
            decision.metadata["original_tier"] = decision.tier.value
        
        return decision
    
    def _get_recent_tiers(self, session: Session) -> list[RoutingTier]:
        """Get tiers from recent messages."""
        tiers = []
        
        # Get last N messages
        recent_messages = session.messages[-self.context_window:]
        
        for msg in recent_messages:
            tier_str = msg.get("metadata", {}).get("routing_tier")
            if tier_str:
                try:
                    tiers.append(RoutingTier(tier_str))
                except ValueError:
                    pass
        
        return tiers
    
    def _should_downgrade(self, content: str, scores: ClassificationScores) -> bool:
        """
        Determine if downgrade from complex to simple is appropriate.
        
        Downgrade if:
        1. Very short message (<20 words)
        2. High simple_indicators score
        3. No technical terms
        4. Explicit simple intent markers
        """
        word_count = len(content.split())
        
        # Check explicit markers
        simple_markers = ["quick question", "just wondering", "simple question", 
                         "one more thing", "by the way", "unrelated"]
        content_lower = content.lower()
        has_simple_marker = any(marker in content_lower for marker in simple_markers)
        
        # Very short and no technical content
        is_very_short = word_count < 20
        no_technical = scores.technical_terms < 0.2
        high_simple_score = scores.simple_indicators > 0.7
        
        # Allow downgrade if multiple conditions met
        conditions_met = sum([
            has_simple_marker,
            is_very_short and no_technical,
            high_simple_score and no_technical,
        ])
        
        return conditions_met >= 2
    
    def _record_feedback(
        self,
        content: str,
        client_decision: RoutingDecision,
        llm_decision: RoutingDecision,
    ) -> None:
        """
        Record comparison between client and LLM decisions for learning.
        
        This data is used by the calibration system to improve client-side patterns.
        """
        # Store comparison for later calibration
        comparison = {
            "content_preview": content[:100],
            "client_tier": client_decision.tier.value,
            "client_confidence": client_decision.confidence,
            "llm_tier": llm_decision.tier.value,
            "llm_confidence": llm_decision.confidence,
            "match": client_decision.tier == llm_decision.tier,
        }
        
        # This would be stored and used by CalibrationManager
        # For now, we'll just note it in the decision metadata
        client_decision.metadata["feedback_recorded"] = True
        llm_decision.metadata["feedback_comparison"] = comparison
