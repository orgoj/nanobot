"""LLM-assisted router for uncertain classifications."""

import json
from typing import Any, Optional

from nanobot.providers.base import LLMProvider

from .models import ClassificationScores, RoutingDecision, RoutingTier


# Enhanced classification prompt with CODING tier and context awareness
CLASSIFICATION_PROMPT = """You are a routing classifier for an AI assistant called nanobot.

Your task is to classify user messages into ONE of these five tiers:

TIER 1 - SIMPLE (Quick facts, social interactions):
- Quick questions, facts, definitions, translations
- Simple calculations, date/time queries
- Social interactions: greetings, thanks, goodbyes, affirmations
- Examples: "What's 2+2?", "Good morning!", "Thanks!", "Good night", "Great job!", "See you tomorrow!"
- Characteristics: <50 tokens, single answer, no tools needed

TIER 2 - MEDIUM (Explanations, discussions, simple coding):
- Explanations with examples (not implementations)
- Web searches, documentation reading
- Simple file operations, git commands, package installs
- Data analysis, comparisons, recommendations
- Examples: 
  "Explain async/await" (explanation)
  "Search React best practices" (search)
  "git status" (git command)
  "npm install" (package install)
  "Compare React vs Vue" (comparison)
- Characteristics: 50-200 tokens, may use tools, coding knowledge but not complex implementation

TIER 3 - CODING (Implementation, development tasks):
- Writing/implementing functions, classes, algorithms
- Debugging code, fixing bugs
- Database queries, API endpoints
- Build, test, deploy operations
- Examples:
  "Write a function to sort an array" (implementation)
  "Fix this bug" (debugging)
  "Create SQL query" (database)
  "Debug race condition" (complex debugging)
  "docker build" (deployment)
  "run tests" (testing)
- Characteristics: 200-800 tokens, definitely uses tools, requires coding expertise

TIER 4 - COMPLEX (Multi-step, architecture, debugging):
- Complex algorithms, system design
- Debugging tricky issues, performance optimization
- Refactoring large codebases, architectural decisions
- Security reviews, distributed systems
- Examples: 
  "Debug distributed system failure" (system debugging)
  "Design database schema" (architecture)
  "Refactor 1000-line function" (large refactoring)
  "Optimize for performance" (optimization)
- Characteristics: 200-1000 tokens, deep analysis, multiple steps

TIER 5 - REASONING (Proofs, logic, mathematics):
- Formal proofs, mathematical derivations
- Step-by-step logical reasoning
- Complex problem-solving with careful analysis
- Theorems, algorithms analysis
- Examples: 
  "Prove this theorem" (proof)
  "Walk me through algorithm" (step-by-step)
  "Analyze time complexity" (analysis)
  "Mathematical proof" (formal)
- Characteristics: >1000 tokens, chains of logic, careful reasoning

SPECIAL NOTES:
- If user says "explain" or "describe" about code → MEDIUM (not CODING)
- If user says "write" or "implement" code → CODING
- If user says "don't write code, just explain" → MEDIUM (explanation, not implementation)
- Social interactions (greetings, thanks) are always SIMPLE
- Git commands, npm install, docker operations are typically CODING tier

Respond ONLY with a JSON object:
{
    "tier": "SIMPLE|MEDIUM|CODING|COMPLEX|REASONING",
    "confidence": 0.0-1.0,
    "reasoning": "One sentence explaining why this tier was chosen",
    "estimated_tokens": 50|200|800|1000|2000,
    "needs_tools": true|false
}

User message to classify:
"""


class ClassificationContext:
    """Context from Layer 1 classification."""
    def __init__(
        self,
        action_type: str = "general",
        has_negations: bool = False,
        negation_details: list = None,
        has_code_blocks: bool = False,
        question_type: Optional[str] = None,
        urgency: list = None,
    ):
        self.action_type = action_type
        self.has_negations = has_negations
        self.negation_details = negation_details or []
        self.has_code_blocks = has_code_blocks
        self.question_type = question_type
        self.urgency = urgency or []


class LLMRouter:
    """LLM-assisted classification for uncertain cases."""
    
    def __init__(
        self,
        provider: LLMProvider,
        model: str = "gpt-4o-mini",
        timeout_ms: int = 500,
        secondary_model: str | None = None,
    ):
        self.provider = provider
        self.model = model
        self.timeout_ms = timeout_ms
        self.secondary_model = secondary_model
    
    async def classify(
        self, 
        content: str,
        context: Optional[ClassificationContext] = None
    ) -> RoutingDecision:
        """
        Classify content using LLM assistance.
        
        Args:
            content: The message/content to classify
            context: Optional context from Layer 1 (action_type, negations, etc.)
        
        Returns:
            RoutingDecision with LLM-determined tier
        """
        # Build classification prompt with context
        prompt = self._build_prompt(content, context)
        
        messages = [
            {
                "role": "system",
                "content": "You are a routing classifier. Respond ONLY with valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            # Call LLM with short timeout
            response = await self._call_llm(messages)
            
            # Parse JSON response
            result = self._parse_response(response)
            
            # Validate against context if provided
            if context:
                result = self._validate_with_context(result, context)
            
            return RoutingDecision(
                tier=RoutingTier(result["tier"].lower()),
                model="",  # Will be filled by tier config
                confidence=result["confidence"],
                layer="llm",
                reasoning=result["reasoning"],
                estimated_tokens=result["estimated_tokens"],
                needs_tools=result["needs_tools"],
                metadata={
                    "llm_model": self.model,
                    "raw_response": response,
                    "context_action_type": context.action_type if context else None,
                    "context_has_negations": context.has_negations if context else None,
                },
            )
            
        except Exception as e:
            # Fallback to secondary model if configured, then to MEDIUM on failure
            if self.secondary_model:
                try:
                    response = await self._call_llm(messages, model=self.secondary_model)
                    result = self._parse_response(response)
                    
                    if context:
                        result = self._validate_with_context(result, context)
                    
                    return RoutingDecision(
                        tier=RoutingTier(result["tier"].lower()),
                        model="",
                        confidence=result["confidence"],
                        layer="llm",
                        reasoning=result["reasoning"],
                        estimated_tokens=result["estimated_tokens"],
                        needs_tools=result["needs_tools"],
                        metadata={
                            "llm_primary": self.model,
                            "llm_secondary": self.secondary_model,
                            "raw_response": response,
                        },
                    )
                except Exception:
                    pass
            
            # Fallback to medium tier on error
            return RoutingDecision(
                tier=RoutingTier.MEDIUM,
                model="",
                confidence=0.5,
                layer="llm",
                reasoning=f"Error in LLM classification: {str(e)}. Defaulting to medium tier.",
                estimated_tokens=200,
                needs_tools=True,
                metadata={"error": str(e)},
            )
    
    def _build_prompt(self, content: str, context: Optional[ClassificationContext]) -> str:
        """Build classification prompt with optional context hints."""
        prompt = CLASSIFICATION_PROMPT + content
        
        if context:
            context_hints = []
            
            # Action type hints
            if context.action_type == "explain":
                context_hints.append(
                    "\nContext: User is asking for EXPLANATION/DESCRIPTION, not implementation. "
                    "If this involves code, consider MEDIUM tier (not CODING)."
                )
            elif context.action_type == "write":
                context_hints.append(
                    "\nContext: User wants IMPLEMENTATION/WRITING. "
                    "If this involves code, consider CODING tier."
                )
            elif context.action_type == "analyze":
                context_hints.append(
                    "\nContext: User wants ANALYSIS/DEBUGGING. "
                    "Consider appropriate tier based on complexity."
                )
            elif context.action_type == "fix":
                context_hints.append(
                    "\nContext: User wants FIXING/REPAIRING something. "
                    "Consider COMPLEX tier if debugging, CODING if code fix."
                )
            
            # Negation hints
            if context.has_negations and context.negation_details:
                negations_str = ", ".join([n.get('negation', 'unknown') for n in context.negation_details[:3]])
                context_hints.append(
                    f"\nContext: Message contains negations: '{negations_str}'. "
                    f"User may be rejecting certain approaches or requesting alternative."
                )
            
            # Code block hint
            if context.has_code_blocks:
                context_hints.append(
                    "\nContext: Code blocks are present in the message. "
                    "Technical discussion detected."
                )
            
            # Question type hint
            if context.question_type == "yes_no":
                context_hints.append(
                    "\nContext: Yes/no question detected. Likely SIMPLE tier."
                )
            
            # Urgency hint
            if context.urgency:
                urgency_str = ", ".join(context.urgency[:2])
                context_hints.append(
                    f"\nContext: Urgency detected: '{urgency_str}'. "
                    f"User needs quick response."
                )
            
            if context_hints:
                prompt += "\n" + "\n".join(context_hints)
        
        return prompt
    
    def _validate_with_context(
        self, 
        result: dict, 
        context: ClassificationContext
    ) -> dict:
        """
        Validate and potentially adjust LLM result based on Layer 1 context.
        
        This ensures consistency between Layer 1 and Layer 2 decisions.
        """
        tier = result["tier"].upper()
        confidence = result["confidence"]
        
        # Rule 1: If action is "explain" and LLM chose CODING, consider MEDIUM
        if context.action_type == "explain" and tier == "CODING":
            # Check if it's explaining code (should be MEDIUM, not CODING)
            if context.has_code_blocks or any(
                word in result["reasoning"].lower() 
                for word in ["explain", "description", "understand"]
            ):
                result["tier"] = "MEDIUM"
                result["confidence"] = min(0.95, confidence + 0.1)
                result["reasoning"] += " (Adjusted: explanation mode, not implementation)"
                result["estimated_tokens"] = 200
        
        # Rule 2: If action is "write" and LLM chose MEDIUM, consider CODING
        if context.action_type == "write" and tier == "MEDIUM":
            if context.has_code_blocks or any(
                word in result["reasoning"].lower()
                for word in ["implement", "code", "function", "write"]
            ):
                result["tier"] = "CODING"
                result["confidence"] = min(0.95, confidence + 0.1)
                result["reasoning"] += " (Adjusted: implementation mode)"
                result["estimated_tokens"] = 800
        
        # Rule 3: If has negations and LLM is very confident, reduce confidence slightly
        if context.has_negations and confidence > 0.9:
            result["confidence"] = confidence * 0.95
            result["reasoning"] += " (Note: negations present)"
        
        return result
    
    async def _call_llm(self, messages: list[dict[str, Any]], model: str | None = None) -> str:
        """Call the LLM with timeout."""
        import asyncio
        
        # Create task for LLM call
        actual_model = model or self.model
        llm_task = asyncio.create_task(
            self.provider.chat(
                messages=messages,
                model=actual_model,
                max_tokens=200,  # Short response needed
                temperature=0.1,  # Low temperature for consistency
            )
        )
        
        # Wait with timeout
        try:
            response = await asyncio.wait_for(
                llm_task,
                timeout=self.timeout_ms / 1000.0
            )
            return response.content or ""
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM classification timed out after {self.timeout_ms}ms")
    
    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse LLM JSON response."""
        # Clean up response - sometimes LLM adds markdown or extra text
        content = content.strip()
        
        # Extract JSON if wrapped in markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        # Parse JSON
        result = json.loads(content)
        
        # Validate required fields
        required = ["tier", "confidence", "reasoning", "estimated_tokens", "needs_tools"]
        for field in required:
            if field not in result:
                raise ValueError(f"Missing required field: {field}")
        
        # Normalize tier
        result["tier"] = result["tier"].upper()
        valid_tiers = ["SIMPLE", "MEDIUM", "COMPLEX", "CODING", "REASONING"]
        if result["tier"] not in valid_tiers:
            raise ValueError(f"Invalid tier: {result['tier']}")
        
        # Normalize confidence
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        
        # Normalize estimated_tokens to standard values (including 800 for CODING)
        tokens = int(result["estimated_tokens"])
        if tokens <= 100:
            result["estimated_tokens"] = 50
        elif tokens <= 500:
            result["estimated_tokens"] = 200
        elif tokens <= 900:  # CODING tier range
            result["estimated_tokens"] = 800
        elif tokens <= 1500:
            result["estimated_tokens"] = 1000
        else:
            result["estimated_tokens"] = 2000
        
        # Normalize needs_tools
        if isinstance(result["needs_tools"], str):
            result["needs_tools"] = result["needs_tools"].lower() == "true"
        else:
            result["needs_tools"] = bool(result["needs_tools"])
        
        return result
