"""Context pipeline stage for model routing."""

from pathlib import Path
from typing import Any, Optional

from nanobot.config.schema import RoutingConfig
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session

from ..router.calibration import CalibrationManager
from ..router.classifier import ClientSideClassifier
from ..router.llm_router import LLMRouter
from ..router.models import RoutingDecision
from ..router.sticky import StickyRouter


class RoutingContext:
    """Context object for routing decisions."""
    
    def __init__(
        self,
        message: Any,
        session: Session,
        default_model: str,
        config: RoutingConfig,
    ):
        self.message = message
        self.session = session
        self.model = default_model
        self.config = config
        self.decision: Optional[RoutingDecision] = None
        self.metadata: dict[str, Any] = {}
    
    def apply_decision(self, decision: RoutingDecision) -> None:
        """Apply routing decision to context."""
        self.decision = decision
        
        # Map tier to model
        tier_config = getattr(self.config.tiers, decision.tier.value, None)
        if tier_config:
            self.model = tier_config.model
            # Store secondary model for fallback
            self.metadata["secondary_model"] = tier_config.secondary_model
        
        self.metadata["routing_tier"] = decision.tier.value
        self.metadata["routing_confidence"] = decision.confidence
        self.metadata["routing_layer"] = decision.layer


class RoutingStage:
    """
    Pipeline stage for intelligent model routing.
    
    Implements two-layer classification with sticky routing:
    1. Client-side pattern matching (fast)
    2. LLM-assisted classification (fallback)
    """
    
    def __init__(
        self,
        config: RoutingConfig,
        provider: Optional[LLMProvider] = None,
        workspace: Optional[Path] = None,
        cron_service: Optional[Any] = None,
    ):
        self.config = config
        self.provider = provider
        self.workspace = workspace
        self._cron_service = cron_service  # Reference to check for scheduled calibration jobs
        
        # Initialize components
        self._init_classifier()
        self._init_calibration()
        
        # OPTIMIZATION: Throttle calibration checks to reduce overhead
        # Check every N requests instead of every single request
        self._calibration_check_counter = 0
        self._calibration_check_interval = 100  # Check every 100 requests
    
    def _init_classifier(self) -> None:
        """Initialize the classification components."""
        # Client-side classifier
        patterns_file = None
        if self.workspace:
            patterns_file = self.workspace / "memory" / "ROUTING_PATTERNS.json"
        
        self.client_classifier = ClientSideClassifier(
            patterns_file=patterns_file,
            min_confidence=self.config.client_classifier.min_confidence,
        )
        
        # LLM router (if provider available)
        self.llm_router: Optional[LLMRouter] = None
        if self.provider:
            self.llm_router = LLMRouter(
                provider=self.provider,
                model=self.config.llm_classifier.model,
                timeout_ms=self.config.llm_classifier.timeout_ms,
                secondary_model=self.config.llm_classifier.secondary_model,
            )
        
        # Sticky router (combines both layers)
        self.sticky_router = StickyRouter(
            client_classifier=self.client_classifier,
            llm_router=self.llm_router,
            context_window=self.config.sticky.context_window,
            downgrade_confidence=self.config.sticky.downgrade_confidence,
        )
    
    def _init_calibration(self) -> None:
        """Initialize calibration manager."""
        if self.workspace and self.config.auto_calibration.enabled:
            patterns_file = self.workspace / "memory" / "ROUTING_PATTERNS.json"
            analytics_file = self.workspace / "analytics" / "routing_stats.json"
            
            self.calibration = CalibrationManager(
                patterns_file=patterns_file,
                analytics_file=analytics_file,
                config=self.config.auto_calibration.model_dump(),
            )
        else:
            self.calibration = None
    
    async def execute(self, ctx: RoutingContext) -> RoutingContext:
        """
        Execute routing stage.
        
        Args:
            ctx: Routing context with message and session
        
        Returns:
            Modified context with selected model
        """
        # Run classification with sticky routing
        decision = await self.sticky_router.classify(
            content=ctx.message.content,
            session=ctx.session,
        )
        
        # Apply decision to context
        ctx.apply_decision(decision)
        
        # Record for calibration (fire-and-forget)
        if self.calibration:
            self._record_for_calibration(ctx, decision)
        
        # Check if calibration needed (throttled to reduce overhead)
        # Skip throttling if user has scheduled a calibration cron job
        # (avoids redundant checks when scheduled calibration is active)
        self._calibration_check_counter += 1
        if (self._calibration_check_counter % self._calibration_check_interval == 0 and
            self.calibration and 
            not self._has_scheduled_calibration_job() and  # Skip if cron job exists
            self.calibration.should_calibrate()):
            self._run_calibration()
        
        return ctx
    
    def _record_for_calibration(
        self,
        ctx: RoutingContext,
        decision: RoutingDecision,
    ) -> None:
        """Record classification for future calibration."""
        import asyncio
        
        # Extract context information from decision metadata
        metadata = decision.metadata
        comparison = metadata.get("feedback_comparison", {})
        
        # Determine action type
        action_type = metadata.get("action_type", "general")
        if not action_type and comparison:
            # Try to extract from client decision if available
            action_type = "general"  # Default
        
        # Check for negations
        negations = metadata.get("negations", [])
        has_negations = len(negations) > 0
        
        # Calculate code presence from content
        content = ctx.message.content.lower()
        code_indicators = ["```", "function", "class", "def ", "import ", "code"]
        code_presence = sum(1 for indicator in code_indicators if indicator in content) / len(code_indicators)
        
        # Determine question type
        question_type = self._determine_question_type(ctx.message.content)
        
        record = {
            "content_preview": ctx.message.content[:200],
            "final_tier": decision.tier.value,
            "final_confidence": decision.confidence,
            "layer": decision.layer,
            # NEW: Full context for intelligent calibration
            "action_type": action_type,
            "has_negations": has_negations,
            "negation_details": negations,
            "code_presence": code_presence,
            "question_type": question_type,
            "content_length": len(ctx.message.content),
        }
        
        # Add comparison data if available
        if comparison:
            record.update({
                "client_tier": comparison.get("client_tier"),
                "client_confidence": comparison.get("client_confidence"),
                "llm_tier": comparison.get("llm_tier"),
                "llm_confidence": comparison.get("llm_confidence"),
                "match": comparison.get("match"),
            })
        
        # Fire-and-forget recording
        asyncio.create_task(self._async_record(record))
    
    def _determine_question_type(self, content: str) -> str:
        """Determine the type of question in the content."""
        content_lower = content.lower().strip()
        
        # Check for question words
        wh_words = ["what", "how", "why", "when", "where", "who", "which"]
        for word in wh_words:
            if content_lower.startswith(word + " ") or content_lower.startswith(word + "'s "):
                return f"{word}_question"
        
        # Check for yes/no questions
        if content_lower.startswith(("is ", "are ", "can ", "do ", "does ", "will ", "would ", "could ", "should ", "has ", "have ", "did ", "was ", "were ")):
            return "yes_no_question"
        
        # Check for commands/imperatives
        imperative_starters = ["write", "create", "build", "make", "generate", "implement", "add", "fix", "update", "delete", "remove", "refactor", "explain", "show", "tell", "give"]
        first_word = content_lower.split()[0] if content_lower else ""
        if first_word in imperative_starters:
            return "imperative"
        
        # Check if it's a statement (no question mark)
        if not content.strip().endswith("?"):
            return "statement"
        
        return "unknown"
    
    async def _async_record(self, record: dict) -> None:
        """Async recording to avoid blocking."""
        if self.calibration:
            self.calibration.record_classification(record)
    
    def _run_calibration(self) -> None:
        """Run calibration (fire-and-forget)."""
        import asyncio
        
        async def calibrate_async():
            if self.calibration:
                results = self.calibration.calibrate()
                # Log results
                print(f"Calibration completed: {results}")
        
        asyncio.create_task(calibrate_async())
    
    def _has_scheduled_calibration_job(self) -> bool:
        """
        Check if user has scheduled a calibration cron job.
        
        Returns True if calibration job exists in cron service,
        which means we should skip the throttled per-request calibration checks.
        """
        # Access cron service through agent loop if available
        # Calibration jobs have message="CALIBRATE_ROUTING"
        try:
            # Check if we can access the cron service
            # This is set during agent initialization
            if hasattr(self, '_cron_service') and self._cron_service:
                jobs = self._cron_service.list_jobs()
                for job in jobs:
                    if job.payload.message == "CALIBRATE_ROUTING":
                        return True
            
            # Alternative: check via workspace file
            # Cron jobs are stored in ~/.nanobot/cron/jobs.json
            import json
            cron_file = self.workspace / "cron" / "jobs.json"
            if cron_file.exists():
                data = json.loads(cron_file.read_text())
                for job in data.get("jobs", []):
                    payload = job.get("payload", {})
                    if payload.get("message") == "CALIBRATE_ROUTING":
                        return True
            
            return False
        except Exception:
            # If we can't determine, assume no scheduled job (safe fallback)
            return False
    
    def get_routing_info(self) -> dict[str, Any]:
        """Get current routing configuration and stats."""
        info = {
            "tiers": {
                tier: {
                    "model": getattr(self.config.tiers, tier).model,
                    "cost_per_mtok": getattr(self.config.tiers, tier).cost_per_mtok,
                    "secondary_model": getattr(self.config.tiers, tier).secondary_model,
                }
                for tier in ["simple", "medium", "complex", "reasoning", "coding"]
            },
            "client_confidence_threshold": self.config.client_classifier.min_confidence,
            "llm_classifier": {
                "model": self.config.llm_classifier.model,
                "timeout_ms": self.config.llm_classifier.timeout_ms,
            },
            "sticky": {
                "context_window": self.config.sticky.context_window,
                "downgrade_confidence": self.config.sticky.downgrade_confidence,
            },
        }
        
        if self.calibration:
            info["calibration"] = {
                "enabled": self.config.auto_calibration.enabled,
                "interval": self.config.auto_calibration.interval,
                "last_run": self.calibration._last_calibration.isoformat() if self.calibration._last_calibration else None,
                "total_classifications": len(self.calibration._classifications),
            }
        
        return info
