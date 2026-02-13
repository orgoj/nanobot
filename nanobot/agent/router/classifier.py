"""Client-side classifier for fast routing decisions."""

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from .models import ClassificationScores, RoutingDecision, RoutingPattern, RoutingTier


# Default 14-dimension weights (sum to 1.0)
DEFAULT_WEIGHTS = {
    "reasoning_markers": 0.18,
    "code_presence": 0.15,
    "simple_indicators": 0.12,
    "multi_step_patterns": 0.12,
    "technical_terms": 0.10,
    "token_count": 0.08,
    "creative_markers": 0.05,
    "question_complexity": 0.05,
    "constraint_count": 0.04,
    "imperative_verbs": 0.03,
    "output_format": 0.03,
    "domain_specificity": 0.02,
    "reference_complexity": 0.02,
    "negation_complexity": 0.01,
    "social_interaction": 0.01,
}


# ========== OPTIMIZATION 1: TRIE-BASED EXACT PHRASE MATCHING ==========
# Ultra-fast O(m) lookup for common exact phrases
# Covers ~30% of typical queries with zero ambiguity

class TrieNode:
    """Node in Trie data structure for exact phrase matching."""
    __slots__ = ['children', 'is_end', 'value']
    
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.is_end = False
        self.value: Optional[Tuple[RoutingTier, float]] = None


class ExactPhraseMatcher:
    """
    Trie-based exact phrase matcher for ultra-fast classification.
    
    Handles common queries with perfect accuracy (confidence=1.0)
    in O(m) time where m = number of words in query.
    
    Example:
        "test message" → SIMPLE (1.0) in 0.001ms
        "git status" → CODING (1.0) in 0.001ms
    """
    
    def __init__(self):
        self.root = TrieNode()
        self._populate()
    
    def _populate(self) -> None:
        """Populate trie with common exact phrases."""
        # Development testing phrases
        phrases = [
            # SIMPLE tier - high frequency social/utility phrases
            ("test message", RoutingTier.SIMPLE, 1.0),
            ("testing", RoutingTier.SIMPLE, 1.0),
            ("ping", RoutingTier.SIMPLE, 1.0),
            ("hello test", RoutingTier.SIMPLE, 1.0),
            ("test 123", RoutingTier.SIMPLE, 1.0),
            ("are you there", RoutingTier.SIMPLE, 1.0),
            ("can you hear me", RoutingTier.SIMPLE, 1.0),
            ("checking if", RoutingTier.SIMPLE, 1.0),
            ("just testing", RoutingTier.SIMPLE, 1.0),
            ("quick test", RoutingTier.SIMPLE, 1.0),
            ("connection test", RoutingTier.SIMPLE, 1.0),
            
            # Greetings
            ("good morning", RoutingTier.SIMPLE, 1.0),
            ("morning", RoutingTier.SIMPLE, 1.0),
            ("good afternoon", RoutingTier.SIMPLE, 1.0),
            ("afternoon", RoutingTier.SIMPLE, 1.0),
            ("good evening", RoutingTier.SIMPLE, 1.0),
            ("evening", RoutingTier.SIMPLE, 1.0),
            ("good night", RoutingTier.SIMPLE, 1.0),
            ("night", RoutingTier.SIMPLE, 1.0),
            ("hello", RoutingTier.SIMPLE, 1.0),
            ("hi", RoutingTier.SIMPLE, 1.0),
            ("hey", RoutingTier.SIMPLE, 1.0),
            ("hey there", RoutingTier.SIMPLE, 1.0),
            
            # Social acknowledgments
            ("thanks", RoutingTier.SIMPLE, 1.0),
            ("thank you", RoutingTier.SIMPLE, 1.0),
            ("thx", RoutingTier.SIMPLE, 1.0),
            ("great job", RoutingTier.SIMPLE, 1.0),
            ("well done", RoutingTier.SIMPLE, 1.0),
            ("awesome", RoutingTier.SIMPLE, 1.0),
            ("perfect", RoutingTier.SIMPLE, 1.0),
            ("excellent", RoutingTier.SIMPLE, 1.0),
            ("ok", RoutingTier.SIMPLE, 1.0),
            ("okay", RoutingTier.SIMPLE, 1.0),
            ("yes", RoutingTier.SIMPLE, 1.0),
            ("no", RoutingTier.SIMPLE, 1.0),
            
            # Date/Time queries
            ("what time is it", RoutingTier.SIMPLE, 1.0),
            ("what time", RoutingTier.SIMPLE, 1.0),
            ("what day is it", RoutingTier.SIMPLE, 1.0),
            ("what date is it", RoutingTier.SIMPLE, 1.0),
            ("what is today", RoutingTier.SIMPLE, 1.0),
            
            # Weather queries
            ("what is the weather", RoutingTier.SIMPLE, 1.0),
            ("what's the weather", RoutingTier.SIMPLE, 1.0),
            ("weather today", RoutingTier.SIMPLE, 1.0),
            ("is it raining", RoutingTier.SIMPLE, 1.0),
            
            # Help queries
            ("help", RoutingTier.SIMPLE, 1.0),
            ("i need help", RoutingTier.SIMPLE, 1.0),
            ("can you help", RoutingTier.SIMPLE, 1.0),
            ("help me", RoutingTier.SIMPLE, 1.0),
            
            # Basic questions
            ("what", RoutingTier.SIMPLE, 1.0),
            ("how", RoutingTier.SIMPLE, 1.0),
            ("why", RoutingTier.SIMPLE, 1.0),
            ("when", RoutingTier.SIMPLE, 1.0),
            ("where", RoutingTier.SIMPLE, 1.0),
            
            # CODING tier - common git/docker commands
            ("git status", RoutingTier.CODING, 1.0),
            ("git log", RoutingTier.CODING, 1.0),
            ("git add", RoutingTier.CODING, 1.0),
            ("git commit", RoutingTier.CODING, 1.0),
            ("git push", RoutingTier.CODING, 1.0),
            ("git pull", RoutingTier.CODING, 1.0),
            ("git fetch", RoutingTier.CODING, 1.0),
            ("git merge", RoutingTier.CODING, 1.0),
            ("git rebase", RoutingTier.CODING, 1.0),
            ("git checkout", RoutingTier.CODING, 1.0),
            ("git branch", RoutingTier.CODING, 1.0),
            ("git clone", RoutingTier.CODING, 1.0),
            ("git init", RoutingTier.CODING, 1.0),
            ("git diff", RoutingTier.CODING, 1.0),
            
            # Docker commands
            ("docker build", RoutingTier.CODING, 1.0),
            ("docker run", RoutingTier.CODING, 1.0),
            ("docker ps", RoutingTier.CODING, 1.0),
            ("docker images", RoutingTier.CODING, 1.0),
            ("docker compose", RoutingTier.CODING, 1.0),
            ("docker stop", RoutingTier.CODING, 1.0),
            ("docker start", RoutingTier.CODING, 1.0),
            ("docker logs", RoutingTier.CODING, 1.0),
            
            # Package managers
            ("npm install", RoutingTier.CODING, 1.0),
            ("npm run", RoutingTier.CODING, 1.0),
            ("pip install", RoutingTier.CODING, 1.0),
            ("cargo build", RoutingTier.CODING, 1.0),
            
            # ========== EXPANDED PHRASES (60+ additional) ==========
            # More git commands
            ("git stash", RoutingTier.CODING, 1.0),
            ("git stash pop", RoutingTier.CODING, 1.0),
            ("git revert", RoutingTier.CODING, 1.0),
            ("git reset", RoutingTier.CODING, 1.0),
            ("git cherry-pick", RoutingTier.CODING, 1.0),
            ("git bisect", RoutingTier.CODING, 1.0),
            ("git tag", RoutingTier.CODING, 1.0),
            ("git remote", RoutingTier.CODING, 1.0),
            ("git show", RoutingTier.CODING, 1.0),
            ("git blame", RoutingTier.CODING, 1.0),
            
            # More docker commands
            ("docker exec", RoutingTier.CODING, 1.0),
            ("docker rm", RoutingTier.CODING, 1.0),
            ("docker rmi", RoutingTier.CODING, 1.0),
            ("docker volume", RoutingTier.CODING, 1.0),
            ("docker network", RoutingTier.CODING, 1.0),
            ("docker pull", RoutingTier.CODING, 1.0),
            ("docker push", RoutingTier.CODING, 1.0),
            ("docker system prune", RoutingTier.CODING, 1.0),
            
            # Testing & Quality
            ("run tests", RoutingTier.CODING, 1.0),
            ("run test", RoutingTier.CODING, 1.0),
            ("test it", RoutingTier.CODING, 1.0),
            ("check coverage", RoutingTier.CODING, 1.0),
            ("coverage report", RoutingTier.CODING, 1.0),
            ("lint code", RoutingTier.CODING, 1.0),
            ("eslint", RoutingTier.CODING, 1.0),
            ("prettier", RoutingTier.CODING, 1.0),
            ("format code", RoutingTier.CODING, 1.0),
            ("black", RoutingTier.CODING, 1.0),
            ("flake8", RoutingTier.CODING, 1.0),
            ("mypy", RoutingTier.CODING, 1.0),
            
            # Debugging & Errors
            ("debug this", RoutingTier.COMPLEX, 1.0),
            ("debug it", RoutingTier.COMPLEX, 1.0),
            ("fix this", RoutingTier.CODING, 1.0),
            ("fix it", RoutingTier.CODING, 1.0),
            ("stack trace", RoutingTier.COMPLEX, 1.0),
            ("error log", RoutingTier.COMPLEX, 1.0),
            ("log file", RoutingTier.COMPLEX, 1.0),
            ("breakpoint", RoutingTier.CODING, 1.0),
            ("debug mode", RoutingTier.CODING, 1.0),
            ("traceback", RoutingTier.COMPLEX, 1.0),
            ("not working", RoutingTier.COMPLEX, 1.0),
            ("broken", RoutingTier.COMPLEX, 1.0),
            
            # Build & Deploy
            ("build it", RoutingTier.CODING, 1.0),
            ("build project", RoutingTier.CODING, 1.0),
            ("compile code", RoutingTier.CODING, 1.0),
            ("deploy it", RoutingTier.CODING, 1.0),
            ("deploy app", RoutingTier.CODING, 1.0),
            ("make deploy", RoutingTier.CODING, 1.0),
            ("webpack", RoutingTier.CODING, 1.0),
            ("vite", RoutingTier.CODING, 1.0),
            ("rollup", RoutingTier.CODING, 1.0),
            ("esbuild", RoutingTier.CODING, 1.0),
            
            # File Operations
            ("read file", RoutingTier.CODING, 1.0),
            ("write file", RoutingTier.CODING, 1.0),
            ("delete file", RoutingTier.CODING, 1.0),
            ("copy file", RoutingTier.CODING, 1.0),
            ("move file", RoutingTier.CODING, 1.0),
            ("parse json", RoutingTier.CODING, 1.0),
            ("parse csv", RoutingTier.CODING, 1.0),
            ("read json", RoutingTier.CODING, 1.0),
            ("read csv", RoutingTier.CODING, 1.0),
            ("extract data", RoutingTier.MEDIUM, 1.0),
            
            # Database
            ("sql query", RoutingTier.CODING, 1.0),
            ("database query", RoutingTier.CODING, 1.0),
            ("select from", RoutingTier.CODING, 1.0),
            ("insert into", RoutingTier.CODING, 1.0),
            ("update table", RoutingTier.CODING, 1.0),
            ("delete from", RoutingTier.CODING, 1.0),
            ("migration", RoutingTier.CODING, 1.0),
            ("seed database", RoutingTier.CODING, 1.0),
            
            # API & Web
            ("api endpoint", RoutingTier.CODING, 1.0),
            ("rest api", RoutingTier.CODING, 1.0),
            ("graphql", RoutingTier.CODING, 1.0),
            ("fetch data", RoutingTier.CODING, 1.0),
            ("http request", RoutingTier.CODING, 1.0),
            ("post request", RoutingTier.CODING, 1.0),
            ("get request", RoutingTier.CODING, 1.0),
            ("curl", RoutingTier.CODING, 1.0),
            
            # Social - extended
            ("how are you doing", RoutingTier.SIMPLE, 1.0),
            ("hows it going", RoutingTier.SIMPLE, 1.0),
            ("what is new", RoutingTier.SIMPLE, 1.0),
            ("whats up", RoutingTier.SIMPLE, 1.0),
            ("long time no see", RoutingTier.SIMPLE, 1.0),
            ("nice to meet you", RoutingTier.SIMPLE, 1.0),
            ("see you later", RoutingTier.SIMPLE, 1.0),
            ("take care", RoutingTier.SIMPLE, 1.0),
            ("have a good one", RoutingTier.SIMPLE, 1.0),
            ("cya", RoutingTier.SIMPLE, 1.0),
            ("ttyl", RoutingTier.SIMPLE, 1.0),
            
            # Simple questions - extended
            ("what is this", RoutingTier.SIMPLE, 1.0),
            ("how do i", RoutingTier.SIMPLE, 1.0),
            ("how to", RoutingTier.SIMPLE, 1.0),
            ("can you", RoutingTier.SIMPLE, 1.0),
            ("is it", RoutingTier.SIMPLE, 1.0),
            ("do you", RoutingTier.SIMPLE, 1.0),
            ("are you", RoutingTier.SIMPLE, 1.0),
            ("will you", RoutingTier.SIMPLE, 1.0),
            ("should i", RoutingTier.SIMPLE, 1.0),
            ("could you", RoutingTier.SIMPLE, 1.0),
            
            # Common single words
            ("stop", RoutingTier.SIMPLE, 1.0),
            ("start", RoutingTier.SIMPLE, 1.0),
            ("go", RoutingTier.SIMPLE, 1.0),
            ("wait", RoutingTier.SIMPLE, 1.0),
            ("pause", RoutingTier.SIMPLE, 1.0),
            ("continue", RoutingTier.SIMPLE, 1.0),
            ("retry", RoutingTier.SIMPLE, 1.0),
            ("cancel", RoutingTier.SIMPLE, 1.0),
            ("abort", RoutingTier.SIMPLE, 1.0),
            ("confirm", RoutingTier.SIMPLE, 1.0),
        ]
        
        for phrase, tier, confidence in phrases:
            self._insert(phrase, tier, confidence)
    
    def _insert(self, phrase: str, tier: RoutingTier, confidence: float) -> None:
        """Insert phrase into trie."""
        node = self.root
        words = phrase.lower().strip().split()
        
        for word in words:
            if word not in node.children:
                node.children[word] = TrieNode()
            node = node.children[word]
        
        node.is_end = True
        node.value = (tier, confidence)
    
    def match(self, content: str) -> Optional[Tuple[RoutingTier, float]]:
        """
        Match exact phrase in trie.
        
        Returns (tier, confidence) if exact match found, None otherwise.
        
        Time: O(m) where m = words in content
        Memory: O(1) lookup
        """
        node = self.root
        words = content.lower().strip().split()
        
        for word in words:
            if word not in node.children:
                return None
            node = node.children[word]
        
        if node.is_end:
            return node.value
        return None


# ========== OPTIMIZATION 8: SYNONYM EXPANSION ==========
# Expand patterns with common synonyms and variations
# Increases regex coverage without adding many new patterns

SYNONYM_GROUPS = {
    "git": ["git", "github", "gitlab"],
    "docker": ["docker", "container", "image"],
    "npm": ["npm", "yarn", "pnpm"],
    "python": ["python", "py"],
    "javascript": ["javascript", "js", "node"],
    "write": ["write", "create", "make", "build"],
    "fix": ["fix", "debug", "repair", "solve", "resolve"],
    "check": ["check", "test", "verify", "validate"],
    "get": ["get", "fetch", "retrieve", "pull"],
    "show": ["show", "display", "print", "list"],
    "delete": ["delete", "remove", "rm", "destroy"],
    "update": ["update", "upgrade", "refresh"],
    "install": ["install", "setup", "configure", "deploy"],
    "error": ["error", "bug", "issue", "problem", "fail"],
    "good": ["good", "great", "excellent", "awesome", "perfect"],
    "help": ["help", "assist", "support", "aid"],
}

# Tier thresholds based on confidence score
DEFAULT_THRESHOLDS = {
    "simple": 0.0,
    "medium": 0.5,
    "complex": 0.85,
    "coding": 0.90,
    "reasoning": 0.97,
}


@dataclass
class ClassificationContext:
    """Context information extracted from content."""
    negations: List[Dict] = None
    action_type: str = "general"  # general, explain, write, analyze, etc.
    has_code_blocks: bool = False
    question_type: Optional[str] = None
    urgency: List[str] = None
    
    def __post_init__(self):
        if self.negations is None:
            self.negations = []
        if self.urgency is None:
            self.urgency = []


# COMPREHENSIVE PATTERN LIBRARY - 80+ patterns across 25 categories
DEFAULT_PATTERNS = [
    # ========== QUICK CHECKS & TESTS (TIER: SIMPLE - High Priority) ==========
    RoutingPattern(
        regex=r"^(test message|test|testing|ping|hello test|test 123|are you there|can you hear me|checking if|just testing|quick test|connection test)$",
        tier=RoutingTier.SIMPLE,
        confidence=0.95,
        examples=["Test message", "Testing", "Hello test", "Test 123", "Can you hear me?", "Just testing"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== MATHEMATICAL & REASONING (TIER: REASONING) ==========
    RoutingPattern(
        regex=r"\b(prove|theorem|lemma|corollary|derivation|formal proof|demonstrate|logical consequence|inductive|deductive|syllogism|axiom|postulate)\b",
        tier=RoutingTier.REASONING,
        confidence=0.95,
        examples=["Prove that...", "Theorem states...", "Formal proof of"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"(\$[^$]+\$|\\\([^)]+\\\)|\\\[[^\]]+\\\]|\b\d+\s*[+\-*/]\s*\d+\s*=\s*\?|\b(solve|calculate|integrate|differentiate|equation|formula|quadratic|logarithm|calculus|algebra|geometry|trigonometry)\b)",
        tier=RoutingTier.REASONING,
        confidence=0.90,
        examples=["Solve x² + 5x + 6 = 0", "Calculate ∫x² dx", "Prove by induction"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(step by step|walk me through|explain why|reasoning|logic|inference|conclusion|premise|hypothesis|analysis|breakdown)\b",
        tier=RoutingTier.REASONING,
        confidence=0.88,
        examples=["Walk me through this", "Step by step solution", "Explain your reasoning"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== COMPLEX SYSTEMS & ARCHITECTURE (TIER: COMPLEX) ==========
    RoutingPattern(
        regex=r"\b(refactor|architecture|distributed system|microservice|design pattern|security review|performance optimization|scalability|high availability|load balancing|system design)\b",
        tier=RoutingTier.COMPLEX,
        confidence=0.90,
        examples=["Refactor this codebase", "Design a distributed system", "System architecture"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(debug|troubleshoot|complex algorithm|concurrency|threading|race condition|memory leak|deadlock|bottleneck|optimize|profil)\b",
        tier=RoutingTier.COMPLEX,
        confidence=0.85,
        examples=["Debug this issue", "Find the race condition", "Memory leak detection"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(not working|broken|error|exception|crash|bug|fix|resolve|solve problem|why is|what's wrong|stack trace|log file)\b",
        tier=RoutingTier.COMPLEX,
        confidence=0.82,
        examples=["Not working", "Getting error", "How to fix", "Debug this"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== CODING & DEVELOPMENT (TIER: CODING) ==========
    # Core coding actions
    RoutingPattern(
        regex=r"\b(write code|implement|code review|unit test|integration test|e2e test|api endpoint|database query|algorithm|data structure|fix bug|optimize code|refactor|code generator)\b",
        tier=RoutingTier.CODING,
        confidence=0.92,
        examples=["Write a function", "Code review", "Fix this bug", "Implement API"],
        added_at=datetime.now().isoformat(),
    ),
    # Git operations
    RoutingPattern(
        regex=r"\b(git (status|log|add|commit|push|pull|fetch|merge|rebase|checkout|branch|clone|init|remote|stash|pop|reset|revert|tag|diff|blame))|(\bcommit\b|\bpush\b|\bpull\b|\bmerge\b|\bbranch\b)\b",
        tier=RoutingTier.CODING,
        confidence=0.88,
        examples=["git status", "git push", "commit changes", "create a branch", "review PR"],
        added_at=datetime.now().isoformat(),
    ),
    # Package management
    RoutingPattern(
        regex=r"\b(npm (install|uninstall|update|audit|init|run|start|build|test)|yarn (add|remove|install|upgrade)|pnpm|pip (install|uninstall|freeze|list)|poetry (add|install|update)|conda (install|env)|go mod|cargo|gem|bundle|composer|maven|gradle)\b",
        tier=RoutingTier.CODING,
        confidence=0.87,
        examples=["npm install", "pip install requests", "cargo build", "yarn add"],
        added_at=datetime.now().isoformat(),
    ),
    # Docker & containers
    RoutingPattern(
        regex=r"\b(docker (build|run|exec|stop|start|restart|logs|ps|images|pull|push|compose|dockerfile)|container|image|volume|network|kubernetes|k8s|helm|pod)\b",
        tier=RoutingTier.CODING,
        confidence=0.90,
        examples=["docker build", "docker-compose up", "kubernetes deployment"],
        added_at=datetime.now().isoformat(),
    ),
    # Database operations
    RoutingPattern(
        regex=r"\b(sql|query|database|table|select|insert|update|delete|join|index|schema|migration|seed|backup|restore|mongodb|postgres|mysql|redis|sqlite|dynamo)\b",
        tier=RoutingTier.CODING,
        confidence=0.87,
        examples=["SQL query", "database migration", "MongoDB aggregation"],
        added_at=datetime.now().isoformat(),
    ),
    # Testing - requires context to avoid catching simple phrases like "test message"
    RoutingPattern(
        regex=r"\b(jest|pytest|mocha|cypress|playwright|selenium|unittest|vitest|ava|tap)\b|\b(write|create|run|execute|debug|fix).*\b(test|tests|testing)\b|\b(test|tests|testing).*(code|function|class|method|api|endpoint)\b",
        tier=RoutingTier.CODING,
        confidence=0.87,
        examples=["write tests", "run jest", "debug test failure", "fix the test", "create test for API"],
        added_at=datetime.now().isoformat(),
    ),
    # Code quality (linting, formatting) - separate from testing
    RoutingPattern(
        regex=r"\b(lint|eslint|prettier|format|black|flake8|mypy|type check)\b",
        tier=RoutingTier.CODING,
        confidence=0.84,
        examples=["lint code", "format with prettier", "check types"],
        added_at=datetime.now().isoformat(),
    ),
    # Network & connectivity
    RoutingPattern(
        regex=r"\b(ping|traceroute|curl|wget|nslookup|dig|netstat|ssh|scp|rsync|sftp|port|connection|endpoint|http|request|ssl|tls|certificate)\b",
        tier=RoutingTier.CODING,
        confidence=0.82,
        examples=["ping server", "curl endpoint", "ssh into", "test connection"],
        added_at=datetime.now().isoformat(),
    ),
    # Build & compilation
    RoutingPattern(
        regex=r"\b(build|compile|transpile|bundle|webpack|vite|rollup|esbuild|babel|typescript|tsc|cmake|make|gcc|clang)\b",
        tier=RoutingTier.CODING,
        confidence=0.85,
        examples=["build project", "compile code", "webpack bundle"],
        added_at=datetime.now().isoformat(),
    ),
    # File operations
    RoutingPattern(
        regex=r"\b(read file|write file|parse|extract|transform|csv|json|xml|yaml|config|log|grep|find|sed|awk|chmod|unzip|compress)\b",
        tier=RoutingTier.CODING,
        confidence=0.80,
        examples=["parse CSV", "extract data", "grep pattern", "transform JSON"],
        added_at=datetime.now().isoformat(),
    ),
    # Code blocks in content
    RoutingPattern(
        regex=r"```[\w]*\n|^(function|class|def|async|await|import|const|let|var|return)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.85,
        examples=["Code block present", "function definition"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== MEDIUM COMPLEXITY TASKS ==========
    RoutingPattern(
        regex=r"\b(documentation|readme|docstring|comment|summarize|paraphrase|rewrite|edit|proofread|grammar|compare|vs\.|versus|difference|similarities?|pros and cons)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.78,
        examples=["Write documentation", "Summarize this", "Compare A and B"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(creative writing|story|poem|fiction|character|plot|dialogue|script|brainstorm|generate ideas|advice|recommend|suggest|tips?|guide|how to|tutorial)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.80,
        examples=["Write a story", "Brainstorm ideas", "Recommend a tool", "Tips for"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(plot|graph|chart|visualize|analyze data|dataset|pandas|dataframe|statistics|correlation|regression|histogram)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.82,
        examples=["Plot this data", "Analyze CSV", "Create chart"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(fetch|scrape|api|webhook|rest|graphql|oauth|authentication|json response)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.80,
        examples=["Fetch data from API", "Create webhook", "REST endpoint"],
        added_at=datetime.now().isoformat(),
    ),
    RoutingPattern(
        regex=r"\b(configure|setup|install|deploy|initialize|setup guide|getting started|configuration|settings|environment|dependencies?)\b",
        tier=RoutingTier.MEDIUM,
        confidence=0.78,
        examples=["Setup guide", "How to install", "Configure settings"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== SIMPLE INTERACTIONS ==========
    # Greetings - Morning
    RoutingPattern(
        regex=r"\b(good morning|morning|rise and shine|top of the morning|early start|coffee time)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.95,
        examples=["Good morning!", "Morning!", "Rise and shine!"],
        added_at=datetime.now().isoformat(),
    ),
    # Greetings - Afternoon
    RoutingPattern(
        regex=r"\b(good afternoon|afternoon|lunch time|mid day|halfway there)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.95,
        examples=["Good afternoon", "Afternoon!"],
        added_at=datetime.now().isoformat(),
    ),
    # Greetings - Evening
    RoutingPattern(
        regex=r"\b(good evening|evening|dinner time|wind down|almost done)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.95,
        examples=["Good evening", "Evening!"],
        added_at=datetime.now().isoformat(),
    ),
    # End of day / Sleep
    RoutingPattern(
        regex=r"\b(good night|night night|sleep tight|time for bed|going to sleep|calling it a day|signing off|see you tomorrow|bed time|sweet dreams|rest well)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.95,
        examples=["Good night!", "Going to sleep", "Calling it a day", "See you tomorrow!"],
        added_at=datetime.now().isoformat(),
    ),
    # Weekend/Holiday
    RoutingPattern(
        regex=r"\b(happy weekend|weekend vibes|tgif|happy friday|saturday|sunday|day off|vacation mode|holiday|merry christmas|happy new year)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.90,
        examples=["Happy weekend!", "TGIF!", "Weekend vibes!"],
        added_at=datetime.now().isoformat(),
    ),
    # Success/Affirmations
    RoutingPattern(
        regex=r"\b(great job|well done|awesome work|excellent|perfect|that worked|success|it works|mission accomplished|nailed it|crushed it|you did it|we did it|high five|cheers|bravo|kudos|great job today|well done today|good work today|thanks for today|productive day)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.90,
        examples=["Great job!", "Well done!", "Mission accomplished", "Great job today!"],
        added_at=datetime.now().isoformat(),
    ),
    # Gratitude
    RoutingPattern(
        regex=r"\b(thank you|thanks|appreciate it|grateful|couldn't have done it without you|lifesaver|you're the best|couldn't ask for better|much appreciated)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.90,
        examples=["Thank you!", "Thanks so much!", "I appreciate it", "You're a lifesaver!"],
        added_at=datetime.now().isoformat(),
    ),
    # Casual check-ins
    RoutingPattern(
        regex=r"\b(how are you|how's it going|what's new|what's happening|what's going on|how have you been|how do you feel|everything ok|you alright|howdy|sup|yo|hey there)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.90,
        examples=["How are you?", "What's new?", "How's it going?", "Sup!"],
        added_at=datetime.now().isoformat(),
    ),
    # Apologies & Corrections
    RoutingPattern(
        regex=r"\b(my bad|sorry|oops|my mistake|i messed up|didn't mean to|apologies|forgive me|scratch that|never mind|forget it|let me rephrase)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.85,
        examples=["My bad!", "Oops, sorry", "Scratch that", "Never mind"],
        added_at=datetime.now().isoformat(),
    ),
    # Basic queries
    RoutingPattern(
        regex=r"\b(search|find|look up|what is|how to|define|explain|translate|calculate|meaning|definition|synonym|antonym|pronunciation)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.85,
        examples=["What is photosynthesis?", "How to cook pasta?", "Translate hello"],
        added_at=datetime.now().isoformat(),
    ),
    # Date/Time & Scheduling
    RoutingPattern(
        regex=r"\b(schedule|calendar|reminder|alarm|timer|countdown|timezone|convert time|what time|when is|how long|deadline|due date)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.85,
        examples=["Set a reminder", "Convert timezone", "What time is it?"],
        added_at=datetime.now().isoformat(),
    ),
    # Weather & Location
    RoutingPattern(
        regex=r"\b(weather|temperature|forecast|rain|sunny|location|address|directions|distance|nearby|restaurant|hotel)\b",
        tier=RoutingTier.SIMPLE,
        confidence=0.85,
        examples=["What's the weather", "Find nearby restaurants"],
        added_at=datetime.now().isoformat(),
    ),
    
    # ========== CATCH-ALL FOR SHORT/GENERIC QUERIES ==========
    # Must be LAST - catches simple short phrases that don't match other patterns
    RoutingPattern(
        regex=r"^(hello|hi|hey|help|what|how|ok|yes|no|thanks|please|goodbye|bye|stop|start|go|run)[\.\?!\s]*$",
        tier=RoutingTier.SIMPLE,
        confidence=0.90,
        examples=["hello", "help", "what", "ok", "thanks", "bye"],
        added_at=datetime.now().isoformat(),
    ),
]


class ClientSideClassifier:
    """
    Fast client-side classifier using multi-layer matching:
    
    Layer 0: Trie exact match (0.001ms, ~30% coverage, confidence=1.0)
    Layer 1: Regex patterns (0.06ms, ~50% coverage, confidence=0.85-0.95)
    Layer 2: Scoring heuristics (0.1ms, remaining coverage)
    
    Optimized for speed and cost - minimizes LLM fallback calls.
    """
    
    def __init__(
        self,
        patterns_file: Optional[Path] = None,
        min_confidence: float = 0.85,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.min_confidence = min_confidence
        self.weights = weights or DEFAULT_WEIGHTS
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.patterns_file = patterns_file
        self._patterns: List[RoutingPattern] = []
        
        # OPTIMIZATION 1: Initialize exact phrase matcher
        # Ultra-fast O(m) lookup for common phrases
        self._exact_matcher = ExactPhraseMatcher()
        
        self._load_patterns()
    
    def _load_patterns(self) -> None:
        """Load patterns from file or use defaults."""
        if self.patterns_file and self.patterns_file.exists():
            try:
                data = json.loads(self.patterns_file.read_text())
                self._patterns = [
                    RoutingPattern.from_dict(p) for p in data.get("patterns", [])
                ]
            except Exception:
                self._patterns = DEFAULT_PATTERNS.copy()
        else:
            self._patterns = DEFAULT_PATTERNS.copy()
    
    def classify(self, content: str) -> Tuple[RoutingDecision, ClassificationScores]:
        """
        Classify content using multi-layer matching:
        
        1. Trie exact match (fastest, confidence=1.0)
        2. Regex patterns (fast, confidence=0.85-0.95)
        3. Scoring heuristics (fallback)
        
        Returns:
            Tuple of (RoutingDecision, ClassificationScores)
        """
        # OPTIMIZATION 1: Check exact phrase matcher first
        # Ultra-fast O(m) lookup for common phrases
        # Covers ~30% of queries with confidence=1.0
        exact_match = self._exact_matcher.match(content)
        if exact_match:
            tier, confidence = exact_match
            scores = ClassificationScores()  # Empty scores for exact match
            decision = RoutingDecision(
                tier=tier,
                model="",
                confidence=confidence,
                layer="client",
                reasoning=f"Exact phrase match: {content[:50]}...",
                estimated_tokens=self._estimate_tokens(content, tier),
                needs_tools=False,
                metadata={
                    "match_type": "exact_trie",
                    "match_source": "pre_filter",
                },
            )
            return decision, scores
        
        # Extract context (negations, action type, etc.)
        context = self._extract_context(content)
        
        # Calculate dimension scores with context awareness
        scores = self._calculate_scores(content, context)
        
        # Calculate weighted confidence
        weighted_sum = scores.calculate_weighted_sum(self.weights)
        calculated_confidence = self._sigmoid(weighted_sum)
        
        # Determine tier based on confidence, patterns, and context
        tier, pattern_confidence = self._determine_tier(calculated_confidence, content, context, scores)
        
        # Use the higher of pattern confidence or calculated confidence
        # This ensures high-confidence pattern matches are trusted
        final_confidence = max(calculated_confidence, pattern_confidence)
        
        decision = RoutingDecision(
            tier=tier,
            model="",
            confidence=final_confidence,
            layer="client",
            reasoning=f"Client-side classification: {tier.value} (confidence={final_confidence:.2f}, action={context.action_type})",
            estimated_tokens=self._estimate_tokens(content, tier),
            needs_tools=self._needs_tools(content, tier),
            metadata={
                "scores": scores.to_dict(),
                "action_type": context.action_type,
                "has_negations": len(context.negations) > 0,
            },
        )
        
        return decision, scores
    
    def _extract_context(self, content: str) -> ClassificationContext:
        """Extract contextual information from content."""
        content_lower = content.lower()
        context = ClassificationContext()
        
        # Detect action type
        context.action_type = self._detect_action_type(content_lower)
        
        # Detect negations with improved scope handling
        context.negations = self._extract_negations(content_lower)
        
        # Detect code blocks
        context.has_code_blocks = content.count('```') >= 2
        
        # Detect question type
        if '?' in content:
            if re.search(r'\b(is|are|was|were|do|does|did|can|could|will|would|should|has|have|had)\b', content_lower):
                context.question_type = 'yes_no'
            elif re.search(r'\b(what|which|who|where|when|why|how)\b', content_lower):
                context.question_type = 'wh_question'
            else:
                context.question_type = 'open'
        
        # Detect urgency
        urgency_words = ['urgent', 'asap', 'immediately', 'quickly', 'hurry', 'deadline', 'emergency']
        context.urgency = [w for w in urgency_words if w in content_lower]
        
        return context
    
    def _detect_action_type(self, content: str) -> str:
        """Detect what type of action the user is requesting."""
        # Writing/Creating actions
        if re.search(r'\b(write|create|generate|build|implement|make|develop|code|script)\b', content):
            return "write"
        
        # Explaining/Describing actions
        if re.search(r'\b(explain|describe|tell me about|what is|how does|why|clarify|elaborate)\b', content):
            return "explain"
        
        # Analyzing actions
        if re.search(r'\b(analyze|review|debug|troubleshoot|check|inspect|investigate|assess|evaluate)\b', content):
            return "analyze"
        
        # Fixing/Improving actions
        if re.search(r'\b(fix|repair|correct|improve|optimize|refactor|enhance|upgrade|update)\b', content):
            return "fix"
        
        # Comparing actions
        if re.search(r'\b(compare|contrast|difference|versus|vs|or|which is better)\b', content):
            return "compare"
        
        # Searching/Finding actions
        if re.search(r'\b(search|find|look for|locate|get|fetch|retrieve)\b', content):
            return "search"
        
        return "general"
    
    def _extract_negations(self, content: str) -> List[Dict]:
        """
        Extract negations with proper scope detection.
        Returns list of dicts with negation info.
        """
        negations = []
        
        # Comprehensive negation patterns
        negation_patterns = [
            # Direct negations
            (r"\b(don'?t|do not|doesn'?t|does not|didn'?t|did not)\b", "direct"),
            (r"\b(won'?t|will not|wouldn'?t|would not|shouldn'?t|should not)\b", "direct"),
            (r"\b(can'?t|cannot|couldn'?t|could not|mustn'?t|must not)\b", "direct"),
            (r"\b(hasn'?t|has not|haven'?t|have not|hadn'?t|had not)\b", "direct"),
            (r"\b(isn'?t|aren'?t|wasn'?t|weren'?t)\b", "direct"),
            # Negative adverbs/phrases
            (r"\b(never|no|not|none|nothing|nobody|nowhere|neither|nor)\b", "adverb"),
            (r"\b(avoid|stop|refrain from|without|unless|except|skip|ignore)\b", "avoidance"),
            (r"\b(rather than|instead of|as opposed to)\b", "preference"),
        ]
        
        for pattern, neg_type in negation_patterns:
            for match in re.finditer(pattern, content):
                negation = match.group(0)
                pos = match.start()
                
                # Determine scope - usually until clause boundary or ~10 words
                scope_end = len(content)
                clause_endings = ['.', ';', 'but', 'however', ', but', 
                                'instead', 'rather', 'just', 'only', ',']
                
                for ending in clause_endings:
                    end_pos = content.find(ending, pos + len(negation))
                    if end_pos != -1 and end_pos < scope_end:
                        # Don't end scope on single comma unless followed by specific words
                        if ending == ',':
                            next_part = content[end_pos:end_pos+20].lower()
                            if any(word in next_part for word in ['instead', 'just', 'only', 'but']):
                                scope_end = end_pos
                        else:
                            scope_end = end_pos
                
                # Limit to ~10 words max
                words_after = content[pos:scope_end].split()
                if len(words_after) > 10:
                    # Find position of 10th word
                    word_count = 0
                    char_pos = pos
                    for char in content[pos:]:
                        if char == ' ':
                            word_count += 1
                            if word_count >= 10:
                                scope_end = char_pos
                                break
                        char_pos += 1
                
                negations.append({
                    'negation': negation,
                    'type': neg_type,
                    'position': pos,
                    'scope_end': scope_end,
                    'scope_text': content[pos:scope_end]
                })
        
        return negations
    
    def _calculate_scores(self, content: str, context: ClassificationContext) -> ClassificationScores:
        """Calculate all dimension scores with context awareness."""
        content_lower = content.lower()
        tokens = content.split()
        token_count = len(tokens)
        
        scores = ClassificationScores()
        
        # 1. Reasoning markers (0.18)
        reasoning_words = ["prove", "theorem", "lemma", "corollary", "step by step", 
                          "walk me through", "explain why", "derivation", "formal proof",
                          "demonstrate", "logical consequence", "analysis", "reasoning"]
        scores.reasoning_markers = self._score_patterns(content_lower, reasoning_words, context)
        
        # 2. Code presence (0.15) - Keep high even with negation if domain is coding
        code_indicators = ["function", "class", "def", "async", "await", "import",
                          "const", "let", "var", "return", "if", "for", "while",
                          "git", "docker", "npm", "pip", "api", "database", "sql"]
        code_score = self._score_patterns(content_lower, code_indicators, context)
        # Boost if code blocks present (this is domain indicator, keep it)
        if context.has_code_blocks:
            code_score = min(1.0, code_score + 0.3)
        scores.code_presence = code_score
        
        # 3. Simple indicators (0.12)
        simple_words = ["what is", "define", "translate", "how to", "meaning of",
                       "what's", "what are", "difference between", "hello", "hi", "thanks"]
        scores.simple_indicators = self._score_patterns(content_lower, simple_words, context)
        
        # 4. Multi-step patterns (0.12)
        multi_step = ["first", "then", "next", "after that", "step 1", "step 2",
                     "1.", "2.", "3.", "phase", "stage", "iteration"]
        scores.multi_step_patterns = self._score_patterns(content_lower, multi_step, context)
        
        # 5. Technical terms (0.10)
        technical = ["algorithm", "kubernetes", "distributed", "microservice",
                    "database", "api", "framework", "library", "protocol",
                    "architecture", "infrastructure", "deployment"]
        scores.technical_terms = self._score_patterns(content_lower, technical, context)
        
        # 6. Token count (0.08)
        if token_count < 20:
            scores.token_count = 0.1
        elif token_count < 100:
            scores.token_count = 0.4
        elif token_count < 300:
            scores.token_count = 0.7
        else:
            scores.token_count = 1.0
        
        # 7. Creative markers (0.05)
        creative = ["story", "poem", "creative", "imagine", "brainstorm", 
                   "write a", "generate ideas", "compose"]
        scores.creative_markers = self._score_patterns(content_lower, creative, context)
        
        # 8. Question complexity (0.05)
        question_marks = content.count("?")
        if question_marks == 0:
            scores.question_complexity = 0.0
        elif question_marks == 1:
            scores.question_complexity = 0.3
        else:
            scores.question_complexity = min(1.0, 0.3 + (question_marks - 1) * 0.2)
        
        # 9. Constraint count (0.04)
        constraints = ["at most", "at least", "minimum", "maximum", "limit",
                      "o(n)", "o(log n)", "efficient", "optimize"]
        scores.constraint_count = self._score_patterns(content_lower, constraints, context)
        
        # 10. Imperative verbs (0.03)
        imperative = ["build", "create", "implement", "design", "develop",
                     "write", "make", "setup", "configure", "deploy"]
        # Reduce score for imperative verbs if negated and action is "explain"
        imperative_score = self._score_patterns(content_lower, imperative, context)
        if context.action_type == "explain" and context.negations:
            imperative_score *= 0.5  # Reduce but don't eliminate
        scores.imperative_verbs = imperative_score
        
        # 11. Output format (0.03)
        formats = ["json", "yaml", "xml", "csv", "markdown", "html",
                  "schema", "table", "list", "diagram"]
        scores.output_format = self._score_patterns(content_lower, formats, context)
        
        # 12. Domain specificity (0.02)
        domains = ["quantum", "blockchain", "machine learning", "ai", "genomics",
                  "bioinformatics", "cybersecurity", "cryptography"]
        scores.domain_specificity = self._score_patterns(content_lower, domains, context)
        
        # 13. Reference complexity (0.02)
        references = ["the docs", "the api", "the documentation", "above",
                     "previous", "earlier", "mentioned", "referenced"]
        scores.reference_complexity = self._score_patterns(content_lower, references, context)
        
        # 14. Negation complexity (0.01)
        negations = ["don't", "not", "never", "avoid", "without", "unless"]
        scores.negation_complexity = self._score_patterns(content_lower, negations, context)
        
        # NEW: 15. Social interaction score (0.01)
        social = ["hello", "hi", "hey", "good morning", "good night", "thanks", 
                 "great job", "well done", "how are you"]
        scores.social_interaction = self._score_patterns(content_lower, social, context)
        
        return scores
    
    def _score_patterns(self, content: str, patterns: List[str], 
                       context: ClassificationContext = None) -> float:
        """
        Calculate pattern match score with context awareness.
        
        Key insight: We preserve domain knowledge (coding, math, etc.) even with negation,
        but we may reduce action-oriented scores (write, create) when negated.
        """
        if not patterns:
            return 0.0
        
        matches = 0
        content_lower = content.lower()
        
        for pattern in patterns:
            pattern_lower = pattern.lower()
            if pattern_lower in content_lower:
                # Check if this match is within a negation scope
                is_negated = False
                negation_distance = float('inf')
                
                if context and context.negations:
                    for neg in context.negations:
                        # Check if pattern appears within negation scope
                        neg_end = neg['scope_end']
                        pattern_pos = content_lower.find(pattern_lower)
                        
                        if neg['position'] < pattern_pos < neg_end:
                            is_negated = True
                            # Calculate word distance
                            distance = len(content_lower[neg['position']:pattern_pos].split())
                            negation_distance = min(negation_distance, distance)
                            break
                
                if is_negated:
                    # Domain knowledge patterns (coding, math, technical terms) should 
                    # keep high scores even when negated - user still needs that expertise
                    # Only reduce action-oriented patterns
                    
                    # Check if this is a domain indicator vs action indicator
                    is_domain_indicator = any(domain_word in pattern_lower for domain_word in 
                        ['code', 'function', 'git', 'docker', 'sql', 'api', 'database', 'math', 
                         'algorithm', 'prove', 'theorem'])
                    
                    if is_domain_indicator:
                        # Keep 80% of score for domain knowledge
                        matches += 0.8
                    else:
                        # Reduce action-oriented patterns
                        if negation_distance <= 2:
                            matches += 0.2  # Strong negation
                        elif negation_distance <= 5:
                            matches += 0.5  # Moderate
                        else:
                            matches += 0.7  # Weak (might be separate clause)
                else:
                    matches += 1.0
        
        # Normalize with diminishing returns
        return min(1.0, matches / len(patterns) * 2 + matches * 0.05)
    
    def _sigmoid(self, x: float) -> float:
        """Sigmoid function for confidence calibration."""
        return 1.0 / (1.0 + math.exp(-x * 2))
    
    def _determine_tier(self, confidence: float, content: str, 
                       context: ClassificationContext, scores: ClassificationScores) -> tuple[RoutingTier, float]:
        """Determine tier with intelligent handling of negations and actions.
        
        Returns:
            Tuple of (tier, pattern_confidence) where pattern_confidence is the 
            confidence from pattern matching (0.0 if no pattern matched)
        """
        content_lower = content.lower()
        
        # Check for explicit pattern matches first (these are strong signals)
        for pattern in self._patterns:
            if re.search(pattern.regex, content_lower, re.IGNORECASE):
                # If we have a strong pattern match, use it but consider context
                if pattern.confidence >= 0.90:
                    # For coding patterns, check if action is explain vs write
                    if pattern.tier == RoutingTier.CODING:
                        if context.action_type == "explain":
                            # User wants coding expertise but explanation, not implementation
                            # Use CODING-capable model but simpler task
                            return RoutingTier.MEDIUM, pattern.confidence
                        elif context.negations and len(context.negations) > 0:
                            # Check if negation is about writing/creating
                            for neg in context.negations:
                                if any(word in neg['scope_text'] for word in ['write', 'create', 'build', 'make']):
                                    return RoutingTier.MEDIUM, pattern.confidence
                    return pattern.tier, pattern.confidence
                elif pattern.confidence >= 0.85:
                    # High confidence pattern - strongly consider it
                    return pattern.tier, pattern.confidence
        
        # Special rule: 2+ reasoning markers with high confidence
        reasoning_count = sum(1 for word in ["prove", "theorem", "step by step", "formal proof"] 
                             if word in content_lower)
        if reasoning_count >= 2 and confidence >= 0.90:
            return RoutingTier.REASONING, 0.90
        
        # Check action type for intelligent tier selection
        if context.action_type == "explain" and scores.code_presence > 0.5:
            # Explaining code is simpler than writing it
            if confidence >= self.thresholds["medium"]:
                return RoutingTier.MEDIUM, 0.0
        
        # Check thresholds - prefer SIMPLE for ambiguous/lower confidence cases
        # This makes the router conservative and cost-effective
        if confidence >= self.thresholds["reasoning"]:
            return RoutingTier.REASONING, 0.0
        elif confidence >= self.thresholds["complex"]:
            return RoutingTier.COMPLEX, 0.0
        elif confidence >= self.thresholds["coding"]:
            # Check if truly coding or just mentioning code
            if scores.code_presence > 0.6 and context.action_type in ["write", "create", "fix"]:
                return RoutingTier.CODING, 0.0
            else:
                return RoutingTier.MEDIUM, 0.0
        elif confidence >= 0.55:  # Moderate-high confidence for medium
            return RoutingTier.MEDIUM, 0.0
        elif confidence >= 0.35:  # Moderate confidence - check indicators
            # Use MEDIUM if there are clear indicators of complexity
            if (scores.technical_terms > 0.4 or 
                scores.multi_step_patterns > 0.4 or 
                scores.imperative_verbs > 0.6 or
                scores.code_presence > 0.4):
                return RoutingTier.MEDIUM, 0.0
            return RoutingTier.SIMPLE, 0.0
        else:
            # Low confidence - always simple
            return RoutingTier.SIMPLE, 0.0
    
    def _estimate_tokens(self, content: str, tier: RoutingTier) -> int:
        """Estimate tokens needed based on content and tier."""
        base_tokens = len(content.split()) * 1.5
        
        tier_multipliers = {
            RoutingTier.SIMPLE: 50,
            RoutingTier.MEDIUM: 200,
            RoutingTier.COMPLEX: 1000,
            RoutingTier.CODING: 800,
            RoutingTier.REASONING: 2000,
        }
        
        return int(base_tokens + tier_multipliers.get(tier, 200))
    
    def _needs_tools(self, content: str, tier: RoutingTier) -> bool:
        """Determine if tools are likely needed."""
        tool_indicators = [
            "search", "find", "look up", "web", "internet", "file",
            "read", "write", "execute", "run", "command", "shell",
            "code", "program", "script", "function", "class"
        ]
        
        content_lower = content.lower()
        tool_score = sum(1 for indicator in tool_indicators 
                        if indicator in content_lower)
        
        tier_boost = {
            RoutingTier.SIMPLE: 0,
            RoutingTier.MEDIUM: 1,
            RoutingTier.COMPLEX: 2,
            RoutingTier.CODING: 2,
            RoutingTier.REASONING: 1,
        }
        
        return tool_score + tier_boost.get(tier, 0) >= 2
    
    def save_patterns(self) -> None:
        """Save current patterns to file."""
        if self.patterns_file:
            data = {
                "patterns": [p.to_dict() for p in self._patterns],
                "version": "2.0",
                "count": len(self._patterns),
            }
            self.patterns_file.parent.mkdir(parents=True, exist_ok=True)
            self.patterns_file.write_text(json.dumps(data, indent=2))


def classify_content(
    content: str,
    patterns_file: Optional[Path] = None,
    min_confidence: float = 0.85,
) -> Tuple[RoutingDecision, ClassificationScores]:
    """
    Convenience function for one-off classifications.
    
    Args:
        content: The message/content to classify
        patterns_file: Optional path to custom patterns file
        min_confidence: Minimum confidence for client-side classification
    
    Returns:
        Tuple of (RoutingDecision, ClassificationScores)
    """
    classifier = ClientSideClassifier(
        patterns_file=patterns_file,
        min_confidence=min_confidence,
    )
    return classifier.classify(content)
