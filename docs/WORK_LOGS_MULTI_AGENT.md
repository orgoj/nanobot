# Work Logs - Multi-Agent Workspace Edition

**Document Version:** 2.1  
**Last Updated:** February 12, 2026  
**Status:** Active Development - Single-Bot Foundation Complete, Multi-Agent Extensions Needed  
**Author:** AI Implementation Team

---

## Status Overview

### ✅ Single-Bot Foundation: COMPLETE
The single-bot work logs implementation is **production ready**. See [WORK_LOGS_SINGLE_BOT.md](../WORK_LOGS_SINGLE_BOT.md) for details.

### 🔄 Multi-Agent Extensions: IN PROGRESS
This document outlines the extensions needed for full multi-agent support.

---

## Integration Notice

**This document has been updated to integrate with the [Multi-Agent Orchestration Architecture](./MULTI_AGENT_ORCHESTRATION_ANALYSIS.md).**

Key integration points:
- Work logs are now **workspace-centric** (like Discord channels)
- Support for **bot-to-bot collaboration** logging
- **Coordinator mode** tracks autonomous decisions
- **Learning Exchange** integration for cross-bot insights
- **Workspace-specific** retention and privacy settings

---

**Document Version:** 1.0  
**Last Updated:** February 12, 2026  
**Status:** Draft - Ready for Review  
**Author:** AI Implementation Team  

## Executive Summary

Based on [VoxYZ research](https://www.voxyz.space/insights/agent-work-logs-beat-polish-trust), this document outlines the implementation of **Raw Work Logs** for nanobot - a transparency feature that shows users the agent's real-time thinking, decision points, corrections, and uncertainty rather than polished final outputs.

**Core Principle:** Users trust AI agents more when they see messy, real-time work logs instead of clean summaries. Raw transparency beats perfection for building confidence.

**Expected Benefits:**
- Increased user trust through verifiable reasoning
- Easier debugging of agent behavior
- Faster identification of errors before they compound
- Reduced "learned helplessness" - users understand *why* decisions were made

---

## Problem Statement

### Current State
- nanobot presents clean, polished outputs
- Users cannot verify reasoning chains
- Errors hidden until they compound
- Smart routing and memory decisions are opaque
- Security scan results shown, but agent reasoning hidden

### User Pain Points
1. **Black Box Effect:** "How did the agent decide to use that skill?"
2. **Hidden Errors:** Mistakes only visible in final output
3. **Overconfidence:** Agent appears certain when it's not
4. **No Learning:** Users can't spot-check reasoning

### Desired State
- Agent shows decision points and reasoning
- Uncertainty exposed with confidence scores
- Corrections and revisions visible
- Process transparency for high-stakes decisions

---

## Implementation Phases

### ✅ Phase 1: Foundation (COMPLETE - Single Bot)
**Goal:** Add work logging infrastructure
**Status:** ✅ **IMPLEMENTED** - See [WORK_LOGS_SINGLE_BOT.md](../WORK_LOGS_SINGLE_BOT.md)

**What Was Completed:**
- ✅ Basic WorkLogEntry with tool execution tracking
- ✅ WorkLog dataclass with session management
- ✅ LogLevel enum (INFO, THINKING, DECISION, CORRECTION, UNCERTAINTY, WARNING, ERROR, TOOL)
- ✅ SQLite storage infrastructure
- ✅ WorkLogManager with CRUD operations
- ✅ CLI commands (explain, how)
- ✅ 33 comprehensive tests

#### 1.2 Multi-Agent Extensions Needed 🔄

**Status:** 🔄 **PENDING** - Add multi-agent fields to existing data model

The current single-bot implementation needs these multi-agent fields added:

**New Log Levels:**
- [ ] `HANDOFF` - Bot-to-bot work transfer
- [ ] `COORDINATION` - Coordinator mode decisions

**New Workspace Context Fields:**
- [ ] `workspace_id: str` - "#general", "#project-refactor"
- [ ] `workspace_type: WorkspaceType` - OPEN, PROJECT, DIRECT, COORDINATION
- [ ] `participants: list[str]` - Bots present in this workspace

**New Bot Identity Fields:**
- [ ] `bot_name: str` - Which bot created entry ("nanobot", "researcher")
- [ ] `bot_role: str` - "coordinator", "specialist", "user-proxy"
- [ ] `triggered_by: str` - "user", "nanobot", "@researcher"

**New Communication Fields:**
- [ ] `mentions: list[str]` - ["@researcher", "@coder"]
- [ ] `response_to: Optional[int]` - Step this responds to
- [ ] `coordinator_mode: bool` - Was nanobot coordinating?
- [ ] `escalation: bool` - Did this trigger user escalation?

**New Learning Exchange Fields:**
- [ ] `shareable_insight: bool` - Can share with other bots?
- [ ] `insight_category: Optional[str]` - "user_preference", "tool_pattern"

**New Methods:**
- [ ] `is_bot_conversation()` - Check if bot-to-bot communication

**Migration Strategy:**
Add optional fields to existing WorkLogEntry with sensible defaults for backward compatibility.

```python
# nanobot/agent/work_log.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum

class LogLevel(Enum):
    INFO = "info"           # Normal operation
    THINKING = "thinking"   # Reasoning steps
    DECISION = "decision"   # Choice made
    CORRECTION = "correction"  # Mistake fixed
    UNCERTAINTY = "uncertainty"  # Low confidence
    WARNING = "warning"     # Issue encountered
    ERROR = "error"         # Failure
    HANDOFF = "handoff"     # Bot-to-bot work transfer
    COORDINATION = "coordination"  # Coordinator mode decisions

class WorkspaceType(Enum):
    OPEN = "open"           # #general - casual, all bots
    PROJECT = "project"     # #project-alpha - focused team
    DIRECT = "direct"       # DM @researcher - 1-on-1
    COORDINATION = "coordination"  # nanobot manages autonomously

@dataclass
class WorkLogEntry:
    timestamp: datetime
    level: LogLevel
    step: int                    # Sequential step number
    category: str                # "memory", "tool", "routing", "security", etc.
    message: str                 # Human-readable description
    
    # Multi-agent context
    workspace_id: str            # "#general", "#project-refactor"
    workspace_type: WorkspaceType
    participants: list[str]      # Bots present in this workspace
    triggered_by: str            # "user", "nanobot", "@researcher", etc.
    
    # Bot identity
    bot_name: str                # Which bot created this entry
    bot_role: str                # "coordinator", "specialist", "user-proxy"
    
    # Decision context
    details: dict = field(default_factory=dict)
    confidence: Optional[float] = None  # 0.0-1.0 for uncertainty
    duration_ms: Optional[int] = None   # How long this step took
    
    # Coordinator mode
    coordinator_mode: bool = False      # Was nanobot coordinating?
    escalation: bool = False            # Did this trigger escalation?
    
    # Tool execution (for agent-to-agent handoffs)
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[Any] = None
    tool_status: Optional[str] = None   # "success", "error", "timeout"
    tool_error: Optional[str] = None
    
    # Cross-bot references (tagging)
    mentions: list[str] = field(default_factory=list)  # ["@researcher", "@coder"]
    response_to: Optional[int] = None   # Step number this responds to
    
    # Learning Exchange
    shareable_insight: bool = False     # Can this be shared with other bots?
    insight_category: Optional[str] = None  # "user_preference", "tool_pattern", etc.
    
    def is_tool_entry(self) -> bool:
        """Check if this entry represents a tool execution."""
        return self.tool_name is not None
    
    def is_bot_conversation(self) -> bool:
        """Check if this is bot-to-bot communication."""
        return self.triggered_by.startswith("@") or self.coordinator_mode
    
    def to_artifact(self) -> dict:
        """Convert to structured artifact for agent consumption."""
        return {
            "step": self.step,
            "workspace": self.workspace_id,
            "bot": self.bot_name,
            "category": self.category,
            "tool": self.tool_name,
            "input": self.tool_input,
            "output": self.tool_output,
            "status": self.tool_status,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "shareable": self.shareable_insight
        }

@dataclass  
class WorkLog:
    session_id: str
    workspace_id: str            # "#general", "#project-refactor", "dm-researcher"
    workspace_type: WorkspaceType
    query: str                   # Original user query or bot trigger
    
    # Participants
    participants: list[str]      # All bots in this workspace
    coordinator: Optional[str]   # "nanobot" if in coordinator mode
    
    # Timing
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # Entries
    entries: list[WorkLogEntry] = field(default_factory=list)
    final_output: Optional[str] = None
    
    # Workspace context
    summary: Optional[str] = None        # AI-generated summary
    artifact_chain: list = field(default_factory=list)  # Structured handoffs
    
    # Learning Exchange integration
    insights_for_sharing: list = field(default_factory=list)  # High-confidence learnings
    
    def add_entry(self, level: LogLevel, category: str, message: str, 
                  bot_name: str = "nanobot", triggered_by: str = "user",
                  details: dict = None, confidence: float = None,
                  coordinator_mode: bool = False) -> WorkLogEntry:
        """Add a work log entry with workspace context."""
        entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=level,
            step=len(self.entries) + 1,
            category=category,
            message=message,
            workspace_id=self.workspace_id,
            workspace_type=self.workspace_type,
            participants=self.participants.copy(),
            triggered_by=triggered_by,
            bot_name=bot_name,
            coordinator_mode=coordinator_mode,
            details=details or {},
            confidence=confidence
        )
        self.entries.append(entry)
        
        # Auto-flag high-confidence insights for Learning Exchange
        if confidence and confidence >= 0.85 and category in ["user_preference", "tool_pattern"]:
            entry.shareable_insight = True
            entry.insight_category = category
            self.insights_for_sharing.append(entry)
        
        return entry
    
    def add_bot_message(self, bot_name: str, message: str, 
                       response_to: Optional[int] = None,
                       mentions: list[str] = None) -> WorkLogEntry:
        """Add a bot-to-bot conversation entry."""
        return self.add_entry(
            level=LogLevel.INFO,
            category="bot_conversation",
            message=f"{bot_name}: {message}",
            bot_name=bot_name,
            triggered_by=bot_name,
            coordinator_mode=(self.coordinator is not None)
        )
    
    def add_escalation(self, reason: str, bot_name: str = "nanobot") -> WorkLogEntry:
        """Log an escalation that needs user attention."""
        return self.add_entry(
            level=LogLevel.COORDINATION,
            category="escalation",
            message=f"🚨 Escalation: {reason}",
            bot_name=bot_name,
            triggered_by=bot_name,
            coordinator_mode=True,
            escalation=True
        )

# Workspace-aware log manager
class WorkspaceWorkLogManager:
    """Manages work logs per workspace (multi-agent support)."""
    
    def __init__(self, enabled: bool = True, storage: str = "sqlite"):
        self.enabled = enabled
        self.storage = storage
        self.active_logs: dict[str, WorkLog] = {}  # workspace_id -> WorkLog
    
    def start_workspace_session(self, workspace_id: str, workspace_type: WorkspaceType,
                               query: str, participants: list[str],
                               coordinator: Optional[str] = None) -> WorkLog:
        """Start a new work log for a workspace."""
        log = WorkLog(
            session_id=f"{workspace_id}-{datetime.now().timestamp()}",
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            query=query,
            participants=participants,
            coordinator=coordinator,
            start_time=datetime.now()
        )
        self.active_logs[workspace_id] = log
        return log
    
    def get_workspace_log(self, workspace_id: str) -> Optional[WorkLog]:
        """Get the active work log for a workspace."""
        return self.active_logs.get(workspace_id)
    
    def end_workspace_session(self, workspace_id: str, final_output: str):
        """End workspace session and queue insights for Learning Exchange."""
        if workspace_id in self.active_logs:
            log = self.active_logs[workspace_id]
            log.end_time = datetime.now()
            log.final_output = final_output
            
            # Queue insights for Learning Exchange
            if log.insights_for_sharing:
                self._queue_for_learning_exchange(log)
            
            self._save_log(log)
            del self.active_logs[workspace_id]
    
    def _queue_for_learning_exchange(self, log: WorkLog):
        """Queue high-confidence insights for cross-bot sharing."""
        from nanobot.learning.exchange import LearningExchange
        
        exchange = LearningExchange()
        for entry in log.insights_for_sharing:
            exchange.queue_insight(
                source_bot=entry.bot_name,
                content=entry.message,
                category=entry.insight_category,
                confidence=entry.confidence,
                workspace=log.workspace_id
            )
```

#### 1.2 WorkLogManager
```python
# nanobot/agent/work_log_manager.py

class WorkLogManager:
    """Manages work logs for agent sessions."""
    
    def __init__(self, enabled: bool = True, storage: str = "sqlite"):
        self.enabled = enabled
        self.storage = storage  # "sqlite", "memory", "file"
        self.current_log: Optional[WorkLog] = None
        
    def start_session(self, session_id: str, query: str) -> WorkLog:
        """Start a new work log session."""
        self.current_log = WorkLog(
            session_id=session_id,
            query=query,
            start_time=datetime.now()
        )
        return self.current_log
    
    def log(self, level: LogLevel, category: str, message: str, 
            details: dict = None, confidence: float = None):
        """Add entry to current log."""
        if not self.enabled or not self.current_log:
            return
        self.current_log.add_entry(level, category, message, details, confidence)
    
    def end_session(self, final_output: str):
        """End current session and save log."""
        if self.current_log:
            self.current_log.end_time = datetime.now()
            self.current_log.final_output = final_output
            self._save_log(self.current_log)
    
    def get_formatted_log(self, mode: str = "summary") -> str:
        """Get formatted log for display.
        
        Modes:
        - "summary": Just high-level steps
        - "detailed": All entries with details
        - "debug": Full technical details
        """
        if not self.current_log:
            return "No work log available"
        
        if mode == "summary":
            return self._format_summary()
        elif mode == "detailed":
            return self._format_detailed()
        elif mode == "debug":
            return self._format_debug()
        else:
            return self._format_summary()
```

#### 1.3 Workspace Integration Points

Work logs are now workspace-aware and integrate with the multi-agent orchestration system:

**Integration Points:**
1. **Workspace Lifecycle**
   - `Workspace.start_session()` → `WorkLogManager.start_workspace_session()`
   - `Workspace.end_session()` → `WorkLogManager.end_workspace_session()`
   - Logs persist per workspace (not global)

2. **Multi-Agent Communication**
   - Bot-to-bot messages logged with `add_bot_message()`
   - @mentions tracked in `mentions` field
   - Coordinator mode decisions flagged

3. **Learning Exchange Pipeline**
   - High-confidence insights auto-queued
   - Shared across workspaces via Learning Exchange
   - Privacy respected (sensitive data filtered)

4. **Coordinator Mode**
   - Autonomous decisions logged separately
   - Escalations clearly marked
   - User notification summaries generated from logs

#### 1.4 Configuration - Workspace-Aware Settings

```json
{
  "work_logs": {
    "enabled": true,
    "storage": "sqlite",
    "retention_days": 30,
    
    "log_levels": ["info", "thinking", "decision", "correction", "uncertainty", "warning", "error", "handoff", "coordination"],
    "categories": ["memory", "tool", "routing", "security", "skill", "context", "general", "bot_conversation", "coordination"],
    
    "workspace_defaults": {
      "open": {
        "log_bot_conversations": false,  # Don't log casual chat
        "log_coordination": false,
        "retention_days": 7  # Shorter retention for casual chats
      },
      "project": {
        "log_bot_conversations": true,   # Log all collaboration
        "log_coordination": true,
        "retention_days": 90  # Keep project logs longer
      },
      "direct": {
        "log_bot_conversations": true,   # Log 1-on-1 discussions
        "log_coordination": false,
        "retention_days": 30
      },
      "coordination": {
        "log_bot_conversations": true,   # Log autonomous decisions
        "log_coordination": true,
        "retention_days": 90,
        "escalation_alerts": true  # Notify user of escalations
      }
    },
    
    "learning_exchange": {
      "enabled": true,
      "min_confidence": 0.85,
      "auto_approve": false,  # User reviews before sharing
      "shareable_categories": ["user_preference", "tool_pattern", "research_finding"]
    },
    
    "show_in_response": false,
    "progressive_disclosure": true,
    "default_mode": "summary",
    "confidence_threshold": 0.7,
    
    "privacy": {
      "mask_secrets": true,
      "workspace_isolation": true,  # Logs don't leak between workspaces
      "user_only_access": true      # Only workspace owner sees logs
    }
  }
}
```

**Workspace-Specific Behaviors:**

- **#general (open):** Lightweight logging, focus on user interactions
- **#project (project):** Full logging, track all collaboration and decisions
- **DM @bot (direct):** Deep logging for expertise sessions
- **#coordination:** Comprehensive logging for autonomous work review

---

### Phase 1.5: Workspace-Specific Work Log Examples

#### Example A: Open Workspace (#general)
**Use case:** Casual conversation, all bots present, user always online

```python
# User asks in #general
log = manager.start_workspace_session(
    workspace_id="#general",
    workspace_type=WorkspaceType.OPEN,
    query="What's the weather like?",
    participants=["nanobot", "researcher", "coder", "social"]
)

# Simple query - nanobot handles directly
log.add_entry(
    level=LogLevel.INFO,
    category="routing",
    message="Simple query - classified as TIER_SIMPLE",
    bot_name="nanobot",
    triggered_by="user",
    confidence=0.95
)

# Tool execution
log.add_entry(
    level=LogLevel.DECISION,
    category="tool",
    message="Calling weather API",
    bot_name="nanobot",
    tool_name="weather_lookup",
    tool_input={"location": "auto-detect"},
    tool_output={"temp": 72, "condition": "sunny"},
    tool_status="success",
    duration_ms=450
)

# Result
log.add_entry(
    level=LogLevel.INFO,
    category="general",
    message="Response delivered to user",
    bot_name="nanobot"
)

log.end_workspace_session("It's 72°F and sunny!")
```

**Log Characteristics:**
- Simple, straightforward flow
- No coordination needed
- Single bot (nanobot) handling everything
- Low complexity, high confidence

---

#### Example B: Project Workspace (#project-refactor)
**Use case:** Focused work with specific team, coordinator mode enabled

```python
# Start project workspace
log = manager.start_workspace_session(
    workspace_id="#project-refactor",
    workspace_type=WorkspaceType.PROJECT,
    query="Refactor the authentication module",
    participants=["nanobot", "researcher", "coder"],
    coordinator="nanobot"  # Coordinator mode active
)

# Initial assessment by coordinator
log.add_entry(
    level=LogLevel.THINKING,
    category="coordination",
    message="Assessing task complexity and required expertise",
    bot_name="nanobot",
    triggered_by="user",
    coordinator_mode=True
)

# Coordinator delegates to researcher
entry = log.add_bot_message(
    bot_name="nanobot",
    message="@researcher Please analyze current auth implementation for security issues",
    mentions=["@researcher"]
)

# Researcher responds
log.add_bot_message(
    bot_name="researcher",
    message="Found 2 issues: (1) Missing rate limiting, (2) Weak password policy",
    response_to=entry.step
)

# Coordinator delegates to coder
log.add_bot_message(
    bot_name="nanobot",
    message="@coder Can you implement rate limiting? @researcher found it as priority #1",
    mentions=["@coder", "@researcher"]
)

# Coder asks for clarification
log.add_bot_message(
    bot_name="coder",
    message="What rate limit should I use? 100 req/min or stricter?"
)

# Low confidence decision - might need user input
log.add_entry(
    level=LogLevel.UNCERTAINTY,
    category="coordination",
    message="Rate limit choice unclear - defaulting to 100/min but user might prefer different",
    bot_name="nanobot",
    coordinator_mode=True,
    confidence=0.6
)

# Decision: Continue with default but note for user review
log.add_entry(
    level=LogLevel.DECISION,
    category="coordination",
    message="Proceeding with 100 req/min, flagging for user confirmation",
    bot_name="nanobot",
    coordinator_mode=True
)

# Coder implements
log.add_entry(
    level=LogLevel.DECISION,
    category="tool",
    message="Implementing rate limiting middleware",
    bot_name="coder",
    tool_name="write_file",
    tool_input={"path": "src/auth/rate_limiter.py"},
    tool_status="success",
    duration_ms=3200
)

# Escalation: Need user decision on password policy
escalation = log.add_escalation(
    reason="Password policy choice: Require special characters (strict) or allow passphrases (user-friendly)?",
    bot_name="nanobot"
)

# Session ends with summary needed
log.summary = """
Project: Auth module refactor
Completed:
- ✓ Security analysis (2 issues found)
- ✓ Rate limiting implemented (100 req/min, needs confirmation)
Pending:
- ⚠ Password policy decision (awaiting user input)
- ⏳ Weak password policy fix
"""

log.end_workspace_session("Progress made! See summary for details.")
```

**Log Characteristics:**
- Multiple bots collaborating
- Coordinator managing flow
- Bot-to-bot conversation tracked
- Escalation triggered for user decision
- Complex workflow with dependencies

---

#### Example C: Direct Message (DM @researcher)
**Use case:** Deep 1-on-1 research discussion, focused expertise

```python
log = manager.start_workspace_session(
    workspace_id="dm-researcher",
    workspace_type=WorkspaceType.DIRECT,
    query="Research quantum computing applications in cryptography",
    participants=["nanobot", "researcher"],
    coordinator=None  # No coordination - direct bot
)

# Researcher takes lead
log.add_entry(
    level=LogLevel.INFO,
    category="context",
    message="Loading researcher expertise context",
    bot_name="researcher"
)

# Deep research with multiple tool calls
log.add_entry(
    level=LogLevel.THINKING,
    category="research",
    message="Beginning literature review on post-quantum cryptography",
    bot_name="researcher"
)

# Multiple search iterations
for query in ["quantum computing cryptography", "post-quantum algorithms", "NIST standards"]:
    log.add_entry(
        level=LogLevel.DECISION,
        category="tool",
        message=f"Searching: {query}",
        bot_name="researcher",
        tool_name="web_search",
        tool_input={"query": query},
        tool_status="success",
        duration_ms=800
    )

# Synthesis (high confidence insight - shareable)
log.add_entry(
    level=LogLevel.DECISION,
    category="research",
    message="Key finding: Shor's algorithm threatens RSA/ECC, lattice-based crypto is leading PQC candidate",
    bot_name="researcher",
    confidence=0.92,  # High confidence - will be shared
    shareable_insight=True,
    insight_category="research_finding"
)

log.end_workspace_session("Comprehensive research report on quantum cryptography...")
```

**Log Characteristics:**
- Single specialist bot (researcher)
- Deep domain expertise
- Multiple tool invocations
- High-confidence insight flagged for sharing
- No coordination needed

---

#### Example D: Coordination Workspace (#coordination-website)
**Use case:** nanobot manages autonomously while user sleeps

```python
log = manager.start_workspace_session(
    workspace_id="#coordination-website",
    workspace_type=WorkspaceType.COORDINATION,
    query="Build company website",
    participants=["nanobot", "researcher", "coder", "creative"],
    coordinator="nanobot",
    # User is offline
)

# nanobot acts as project manager
log.add_entry(
    level=LogLevel.COORDINATION,
    category="coordination",
    message="Coordinator mode activated - user offline, managing autonomously",
    bot_name="nanobot",
    triggered_by="nanobot",
    coordinator_mode=True
)

# Parallel task delegation
log.add_bot_message(
    bot_name="nanobot",
    message="@researcher Analyze 3 competitor websites. @creative Draft homepage designs. @coder Setup repo. Work in parallel.",
    mentions=["@researcher", "@creative", "@coder"]
)

# Bots report progress asynchronously
log.add_bot_message(
    bot_name="researcher",
    message="Competitor analysis complete. Key finding: All use React, average load time 2.3s"
)

log.add_bot_message(
    bot_name="creative",
    message="Drafted 2 designs. Minimalist version: strong performance. Visual version: rich media. Need user choice."
)

log.add_bot_message(
    bot_name="coder",
    message="Repo setup complete. Ready for implementation."
)

# Coordinator synthesizes
log.add_entry(
    level=LogLevel.COORDINATION,
    category="coordination",
    message="Parallel tasks complete. Blocking issues: Design choice (minimalist vs visual).",
    bot_name="nanobot",
    coordinator_mode=True
)

# Decision: Can make low-risk choice
log.add_entry(
    level=LogLevel.DECISION,
    category="coordination",
    message="Choosing minimalist design - better performance aligns with competitor analysis findings",
    bot_name="nanobot",
    coordinator_mode=True,
    confidence=0.85
)

# Delegate implementation
log.add_bot_message(
    bot_name="nanobot",
    message="@coder Proceed with minimalist design. @creative Provide specs to coder.",
    mentions=["@coder", "@creative"]
)

# But wait - creative disagrees
log.add_bot_message(
    bot_name="creative",
    message="Respectfully disagree - visual design better for brand. Suggest A/B testing both?"
)

# Conflict! Must escalate
log.add_escalation(
    reason="Design conflict: Coder wants minimalist (performance), Creative wants visual (brand). Both valid. Need user decision.",
    bot_name="nanobot"
)

# Generate user notification summary
log.summary = """
🌙 Overnight Progress Report (#coordination-website)

✅ COMPLETED:
- Competitor analysis (3 sites reviewed)
- 2 homepage designs drafted
- Repository setup ready

⚠️ NEEDS YOUR DECISION:
Design approach conflict:
- Coder recommends: Minimalist (faster load, better SEO)
- Creative recommends: Visual (stronger brand, richer experience)
- Suggestion: A/B test both versions

⏳ PENDING:
- Finalize design choice
- Begin implementation
- Deploy initial version

Next action needed: Choose design direction
"""

log.end_workspace_session("Progress report generated. Awaiting user decision.")
```

**Log Characteristics:**
- Heavy coordinator activity
- Multiple bots working in parallel
- Conflict resolution attempted
- Escalation when consensus fails
- Rich summary for user notification

---

### ✅ Phase 2: Core Logging (COMPLETE - Single Bot)
**Goal:** Add logging to all major decision points
**Status:** ✅ **IMPLEMENTED** - See [WORK_LOGS_SINGLE_BOT.md](../WORK_LOGS_SINGLE_BOT.md)

**What Was Completed:**
- ✅ AgentLoop session lifecycle integration
- ✅ Routing decision logging with confidence scores
- ✅ Tool execution logging with timing
- ✅ Memory retrieval logging
- ✅ Error logging throughout pipeline
- ✅ Response generation logging

#### 2.2 Multi-Agent Logging Extensions Needed 🔄

**Status:** 🔄 **PENDING** - Add multi-agent specific logging

**New Logging Categories:**

**Workspace Lifecycle Logging:**
```python
# Log workspace creation
work_log.log(
    level=LogLevel.INFO,
    category="workspace",
    message="Created workspace #project-alpha",
    workspace_id="#project-alpha",
    workspace_type=WorkspaceType.PROJECT,
    participants=["nanobot", "researcher", "coder"]
)
```

**Bot-to-Bot Communication Logging:**
```python
# Log when nanobot delegates to researcher
work_log.add_bot_message(
    bot_name="nanobot",
    message="@researcher Please analyze competitors",
    mentions=["@researcher"],
    coordinator_mode=True
)

# Log researcher response
work_log.add_bot_message(
    bot_name="researcher",
    message="Found 3 competitor sites",
    response_to=previous_step
)
```

**Coordinator Mode Logging:**
```python
# Log autonomous coordinator decisions
work_log.log(
    level=LogLevel.COORDINATION,
    category="coordination",
    message="Auto-approved task delegation",
    coordinator_mode=True,
    escalation=False
)

# Log escalations
work_log.add_escalation(
    reason="Tech stack decision needs user input",
    bot_name="nanobot"
)
```

**Bot Identity Tracking:**
```python
# Every entry should include bot identity
work_log.log(
    level=LogLevel.DECISION,
    category="routing",
    message="Classified as complex task",
    bot_name="researcher",  # Which bot made this decision
    bot_role="specialist",
    triggered_by="@nanobot"  # Who triggered this action
)
```
```python
# In nanobot/agent/loop.py

class AgentLoop:
    def __init__(self, ...):
        self.work_log = WorkLogManager(enabled=config.work_logs.enabled)
    
    async def _process_chat_message(self, message: str, ...):
        # Start work log session
        self.work_log.start_session(session_id, message)
        
        try:
            # Log message received
            self.work_log.log(
                level=LogLevel.INFO,
                category="general",
                message=f"Processing user message: {message[:100]}..."
            )
            
            # Log memory retrieval
            self.work_log.log(
                level=LogLevel.THINKING,
                category="memory",
                message="Retrieving relevant context from memory",
                details={"query": message, "limit": 10}
            )
            
            # Build context with detailed logging
            context = self._build_context_with_logging(message)
            
            # Log routing decision
            self.work_log.log(
                level=LogLevel.DECISION,
                category="routing",
                message=f"Classified as {tier} tier",
                details={
                    "tier": tier,
                    "model": model,
                    "confidence": confidence,
                    "alternatives": alternatives
                },
                confidence=confidence
            )
            
            # Execute with logging
            result = await self._execute_with_logging(context)
            
            # Log completion
            self.work_log.end_session(result)
            
            # Return based on mode
            if self.config.work_logs.show_in_response:
                return self._format_response_with_log(result)
            else:
                return result
                
        except Exception as e:
            self.work_log.log(
                level=LogLevel.ERROR,
                category="general",
                message=f"Error processing message: {str(e)}"
            )
            self.work_log.end_session(f"Error: {str(e)}")
            raise
```

#### 2.2 Context Builder Logging
```python
# In nanobot/agent/context.py

def _build_context_with_logging(self, query: str) -> str:
    """Build context with work logging."""
    
    # Log identity loading
    self.work_log.log(
        level=LogLevel.INFO,
        category="context",
        message="Loading agent identity"
    )
    
    # Log memory context retrieval
    self.work_log.log(
        level=LogLevel.THINKING,
        category="memory",
        message="Querying memory for relevant context",
        details={"query_embedding": "BAAI/bge-small-en-v1.5"}
    )
    
    memory = self.memory.get_memory_context()
    
    if memory:
        self.work_log.log(
            level=LogLevel.INFO,
            category="memory",
            message=f"Retrieved {len(memory)} characters of memory context"
        )
    else:
        self.work_log.log(
            level=LogLevel.WARNING,
            category="memory",
            message="No relevant memory context found"
        )
    
    # Log skills loading
    self.work_log.log(
        level=LogLevel.THINKING,
        category="skill",
        message="Loading available skills",
        details={"skill_count": len(skills)}
    )
    
    for skill in skills:
        self.work_log.log(
            level=LogLevel.INFO,
            category="skill",
            message=f"Skill loaded: {skill['name']} ({skill.get('verified', 'unknown')})"
        )
    
    return context
```

#### 2.3 Smart Routing Logging
```python
# In nanobot/agent/stages/routing_stage.py

async def execute(self, context: Context) -> Context:
    """Execute routing with work logging."""
    
    # Log classification start
    self.work_log.log(
        level=LogLevel.THINKING,
        category="routing",
        message="Starting message classification"
    )
    
    # Get classification
    result = await self.classifier.classify(context.message)
    
    # Log decision
    self.work_log.log(
        level=LogLevel.DECISION,
        category="routing",
        message=f"Classified as {result.tier} tier ({result.model})",
        details={
            "tier": result.tier,
            "model": result.model,
            "confidence": result.confidence,
            "patterns_matched": result.patterns,
            "alternatives": result.alternatives
        },
        confidence=result.confidence
    )
    
    # Log if low confidence
    if result.confidence < self.config.work_logs.confidence_threshold:
        self.work_log.log(
            level=LogLevel.UNCERTAINTY,
            category="routing",
            message=f"Low confidence ({result.confidence:.0%}) - consider manual review",
            confidence=result.confidence
        )
    
    return context.with_routing(result)
```

#### 2.4 Tool Execution Logging with Artifacts
```python
# In nanobot/agent/tools/base.py or tool implementations

async def execute_with_logging(self, *args, **kwargs):
    """
    Execute tool with comprehensive logging.
    
    Captures both human-readable descriptions and structured artifacts
    for agent-to-agent handoffs.
    """
    
    start_time = time.time()
    
    # Create tool execution entry with structured input
    entry = self.work_log.add_entry(
        level=LogLevel.DECISION,
        category="tool",
        message=f"Executing {self.name}",
        tool_name=self.name,
        tool_input={
            "args": args,
            "kwargs": {k: str(v)[:500] for k, v in kwargs.items()},  # Truncate large values
            "timestamp": datetime.now().isoformat()
        }
    )
    
    try:
        result = await self._execute(*args, **kwargs)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Serialize result for structured output
        tool_output = self._serialize_for_artifact(result)
        
        # Update entry with structured output
        entry.tool_output = tool_output
        entry.tool_status = "success"
        entry.duration_ms = duration_ms
        
        # Human-readable summary
        entry.message = f"✓ {self.name} completed in {duration_ms}ms"
        entry.details = {
            "result_type": type(result).__name__,
            "result_summary": str(result)[:200],
            "duration_ms": duration_ms,
            "output_size_bytes": len(json.dumps(tool_output))
        }
        
        return result
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Update entry with error information
        entry.tool_status = "error"
        entry.tool_error = str(e)
        entry.duration_ms = duration_ms
        entry.level = LogLevel.ERROR
        entry.message = f"✗ {self.name} failed: {str(e)[:200]}"
        entry.details = {
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
            "duration_ms": duration_ms
        }
        
        raise

    def _serialize_for_artifact(self, result: Any) -> dict:
        """Convert tool result to structured artifact format."""
        if isinstance(result, (dict, list)):
            return result
        elif hasattr(result, 'to_dict'):
            return result.to_dict()
        elif hasattr(result, '__dict__'):
            return {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
        else:
            return {"_value": str(result), "_type": type(result).__name__}
```

#### 2.5 Example: Security Tool Logging

Real-world example of `scan_skill` tool logging:

**Human-Readable Output:**
```
⚠️ Security scan flagged 1 issue (risk: 15/100)

Findings:
- [HIGH] persistence_mechanism: Uses cron scheduling
  This may be a false positive for scheduled bookmark digests
```

**Structured Artifact (for next agent):**
```json
{
  "tool": "scan_skill",
  "input": {"skill_path": "./x-bookmarks", "strict": false},
  "output": {
    "skill_name": "x-bookmarks",
    "risk_score": 15,
    "passed": false,
    "status": "rejected",
    "findings": [
      {
        "severity": "high",
        "category": "persistence_mechanism",
        "confidence": 0.85,
        "line": 8,
        "code": "scheduled bookmark digests via cron",
        "remediation": "Verify this is legitimate scheduled task usage"
      }
    ],
    "critical_count": 0,
    "high_count": 1,
    "medium_count": 0,
    "low_count": 0
  },
  "status": "success",
  "duration_ms": 342,
  "next_actions": ["manual_review", "approve_if_trusted"]
}
```

**Next Agent Can:**
- See risk score: 15/100 (low-medium)
- Understand finding is cron-related
- Know manual approval is recommended
- Access full structured data without parsing text

#### 2.6 Tool Artifact Schema Standards

**Tool Input Schema (all tools):**
```python
{
  "args": [...],                 # Positional arguments (serialized)
  "kwargs": {...},              # Keyword arguments (truncated if large)
  "timestamp": "ISO8601",       # Execution start time
  "caller": "agent-id",         # Which agent/tool called this
  "context": {...}              # Execution context
}
```

**Tool Output Schema (all tools):**
```python
{
  "_raw": {...},                # Original result (if serializable)
  "_type": "class_name",        # Result type for deserialization
  "_summary": "...",            # Human-readable summary
  "status": "success|error",    # Execution status
  "error": "...",              # Error message (if failed)
  "metadata": {...}            # Tool-specific metadata
}
```

---

### Phase 2.5: Workspace-Aware Multi-Agent Artifact Handoffs
**Goal:** Enable work logs as structured artifacts for workspace-based agent collaboration

**Integration with Workspace Architecture:**

Work logs now serve as the **source of truth** for bot-to-bot communication within workspaces. Unlike simple chat messages, they provide:

1. **Structured context** - Bots see full decision history, not just latest message
2. **Confidence scores** - Know when to trust vs verify
3. **Tool execution results** - Structured data, not natural language
4. **Workspace scope** - Artifacts respect workspace boundaries (#general vs #project)

Based on [VoxYZ research on artifact handoffs](https://www.voxyz.space/insights/agents-need-artifact-handoffs-not-chat-reports):

#### Why Artifacts Beat Chat for Multi-Agent Workflows

**Problem with Chat Reports:**
```
Agent A: "I analyzed the data and found 3 issues..."
Agent B: Must parse natural language → Extract data → Act
```

**Solution: Structured Artifacts:**
```python
{
  "analysis_id": "uuid",
  "issues": [
    {"severity": "high", "category": "performance", "metric": 0.15},
    {"severity": "medium", "category": "security", "metric": 0.03}
  ],
  "next_actions": ["optimize_query", "add_index"]
}
```

#### WorkLog as Agent Artifact

```python
# nanobot/agent/work_log.py

@dataclass
class WorkLog:
    # ... existing fields ...
    
    # Artifact metadata for multi-agent handoffs
    artifact_schema: str = "work-log-v1"  # Version for compatibility
    producer_agent: str = "main"          # Agent that created this log
    consumer_agent: Optional[str] = None   # Agent that should consume it
    workflow_id: Optional[str] = None    # Parent workflow identifier
    
    def to_agent_artifact(self) -> dict:
        """
        Convert work log to structured artifact for next agent.
        
        Next agent can directly consume this without parsing text.
        """
        return {
            "schema": self.artifact_schema,
            "workflow_id": self.workflow_id,
            "query": self.query,
            "decisions": [
                {
                    "step": e.step,
                    "category": e.category,
                    "tool": e.tool_name,
                    "input": e.tool_input,
                    "output": e.tool_output,
                    "status": e.tool_status,
                    "confidence": e.confidence,
                    "duration_ms": e.duration_ms,
                    "error": e.tool_error
                }
                for e in self.entries
                if e.is_tool_entry()  # Only tool executions (structured data)
            ],
            "summary": {
                "total_steps": len(self.entries),
                "tool_calls": len([e for e in self.entries if e.is_tool_entry()]),
                "errors": len([e for e in self.entries if e.level == LogLevel.ERROR]),
                "total_duration_ms": sum(e.duration_ms or 0 for e in self.entries),
                "final_output": self.final_output[:500]
            },
            "recommendations": self._extract_next_actions()
        }
    
    def _extract_next_actions(self) -> list[str]:
        """Extract suggested next actions from work log."""
        actions = []
        
        # Look for explicit next_actions in tool outputs
        for entry in self.entries:
            if entry.tool_output and isinstance(entry.tool_output, dict):
                if "next_actions" in entry.tool_output:
                    actions.extend(entry.tool_output["next_actions"])
        
        # Infer from errors
        errors = [e for e in self.entries if e.level == LogLevel.ERROR]
        if errors:
            actions.append("review_errors")
        
        # Infer from low confidence
        low_conf = [e for e in self.entries 
                   if e.confidence and e.confidence < 0.7]
        if low_conf:
            actions.append("verify_low_confidence_decisions")
        
        return actions
```

#### Artifact Storage for Multi-Agent Workflows

```python
# nanobot/agent/artifact_store.py

class AgentArtifactStore:
    """Store and retrieve artifacts for agent-to-agent handoffs."""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path / ".nanobot" / "artifacts"
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def save_artifact(self, artifact: dict, producer: str, consumer: Optional[str] = None) -> str:
        """Save artifact and return artifact ID."""
        artifact_id = str(uuid.uuid4())
        artifact_path = self.storage_path / f"{artifact_id}.json"
        
        artifact["_meta"] = {
            "id": artifact_id,
            "producer": producer,
            "consumer": consumer,
            "created_at": datetime.now().isoformat(),
            "schema": artifact.get("schema", "unknown")
        }
        
        artifact_path.write_text(json.dumps(artifact, indent=2))
        return artifact_id
    
    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Retrieve artifact by ID."""
        artifact_path = self.storage_path / f"{artifact_id}.json"
        if artifact_path.exists():
            return json.loads(artifact_path.read_text())
        return None
    
    def list_artifacts_for_consumer(self, consumer: str) -> list[dict]:
        """List all artifacts waiting for a specific consumer agent."""
        artifacts = []
        for artifact_file in self.storage_path.glob("*.json"):
            data = json.loads(artifact_file.read_text())
            if data.get("_meta", {}).get("consumer") == consumer:
                artifacts.append(data)
        return sorted(artifacts, key=lambda x: x["_meta"]["created_at"])
```

#### Example: Multi-Agent Bookmark Analysis Workflow

```python
# Agent A: Fetch and analyze bookmarks
async def analyze_bookmarks():
    work_log = WorkLogManager().start_session("analyze_bookmarks", "Check my X bookmarks")
    
    # Step 1: Fetch bookmarks
    bookmarks = await exec_tool("bird", {"command": "bookmarks", "count": 50})
    work_log.add_entry(
        tool_name="bird",
        tool_input={"command": "bookmarks", "count": 50},
        tool_output={"count": len(bookmarks), "categories": categorize(bookmarks)},
        tool_status="success",
        duration_ms=1200
    )
    
    # Step 2: Categorize
    categories = categorize_bookmarks(bookmarks)
    work_log.add_entry(
        tool_name="categorize",
        tool_input={"items": len(bookmarks)},
        tool_output={
            "categories": categories,
            "ai_ml_count": categories.get("AI/ML", 0),
            "productivity_count": categories.get("Productivity", 0)
        },
        tool_status="success"
    )
    
    # Convert to artifact for Agent B
    artifact = work_log.to_agent_artifact()
    artifact["next_actions"] = ["summarize_top_categories", "suggest_actions"]
    
    # Save for Agent B
    artifact_id = artifact_store.save_artifact(
        artifact, 
        producer="bookmark_analyzer",
        consumer="action_suggester"
    )
    
    return f"Analysis complete. See artifact {artifact_id} for details."

# Agent B: Read artifact and suggest actions
async def suggest_actions(artifact_id: str):
    artifact = artifact_store.get_artifact(artifact_id)
    
    # Directly access structured data - no parsing!
    ai_ml_count = artifact["decisions"][1]["output"]["ai_ml_count"]
    
    if ai_ml_count > 5:
        return f"You have {ai_ml_count} AI bookmarks. Want me to create a summary report?"
```

**Benefits:**
- No natural language parsing between agents
- Clear data lineage and audit trail
- Structured error handling
- Next action recommendations
- Versioned schemas for compatibility

---

### Phase 2.6: Learning Exchange Integration
**Goal:** Work logs feed insights into the Learning Exchange system

**How It Works:**

When bots collaborate in workspaces, they generate insights. High-confidence insights are automatically queued for the Learning Exchange:

```python
# From WorkLog.add_entry():
if confidence >= 0.85 and category in ["user_preference", "tool_pattern"]:
    entry.shareable_insight = True
    entry.insight_category = category
    log.insights_for_sharing.append(entry)

# When workspace session ends:
def _queue_for_learning_exchange(log: WorkLog):
    """Share valuable insights across bots."""
    exchange = LearningExchange()
    
    for entry in log.insights_for_sharing:
        package = LearningPackage(
            source_bot=entry.bot_name,
            content=entry.message,
            category=entry.insight_category,
            confidence=entry.confidence,
            workspace=log.workspace_id,
            applicable_to=["all"]  # Or infer from context
        )
        exchange.queue_for_exchange(package)
```

**Example Flow:**

1. **User asks in #general:** "I prefer short summaries first"
2. **nanobot logs it:** High confidence (0.95), category="user_preference"
3. **Session ends:** Insight auto-queued for Learning Exchange
4. **Next exchange cycle:** Insight shared with @researcher, @coder, etc.
5. **Other bots learn:** Now all bots know user's preference

**Workspace-Specific Learning:**

```python
# Insights from #general (broad applicability)
"User prefers concise responses" → Share with all bots

# Insights from DM @researcher (specific applicability)
"User likes academic citations in research" → Share only with @researcher

# Insights from #project-alpha (project-specific)
"This project uses React, not Vue" → Share with project team only
```

**Benefits:**
- ✓ Bots learn from each other's experiences
- ✓ User preferences propagate automatically
- ✓ No need to repeat instructions to each bot
- ✓ Workspace-scoped learning (general vs specific)

---

### Phase 3: CLI Integration (Week 3)
**Goal:** Add user-facing commands to view work logs

#### 3.1 New CLI Commands - Workspace-Aware

```python
# In nanobot/cli/commands.py

@app.command("explain")
def explain_last_decision(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", 
                                           help="Workspace to explain (#general, #project-alpha)"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", 
                                            help="Specific session ID"),
    mode: str = typer.Option("detailed", "--mode", "-m",
                            help="Explanation mode: summary, detailed, debug, coordination"),
    bot: Optional[str] = typer.Option(None, "--bot", "-b",
                                     help="Filter by bot (@researcher, @coder)"),
):
    """
    Show how decisions were made in a workspace.
    
    Examples:
        nanobot explain                              # Explain last interaction
        nanobot explain -w #project-refactor         # Explain project workspace
        nanobot explain -w #coordination-website     # See overnight coordination
        nanobot explain --mode coordination          # Focus on coordinator decisions
        nanobot explain -b @researcher               # See what researcher did
    """
    from nanobot.agent.work_log_manager import WorkspaceWorkLogManager
    
    manager = WorkspaceWorkLogManager()
    
    # Get workspace log
    if workspace:
        log = manager.get_workspace_log(workspace)
        if not log:
            console.print(f"[yellow]No active work log for {workspace}.[/yellow]")
            return
    elif session_id:
        log = manager.get_log_by_session(session_id)
    else:
        log = manager.get_last_log()
    
    if not log:
        console.print("[yellow]No work log found. Interact with the agent first.[/yellow]")
        return
    
    # Filter by bot if specified
    if bot:
        entries = [e for e in log.entries if e.bot_name == bot.lstrip("@")]
        console.print(f"[cyan]Showing entries from {bot} in {log.workspace_id}[/cyan]\n")
    else:
        entries = log.entries
        console.print(f"[cyan]Work log for {log.workspace_id} ({log.workspace_type.value})[/cyan]\n")
    
    # Format based on mode
    if mode == "summary":
        console.print(_format_summary(log, entries))
    elif mode == "detailed":
        console.print(_format_detailed(log, entries))
    elif mode == "coordination":
        # Focus on coordinator mode entries
        coord_entries = [e for e in entries if e.coordinator_mode]
        console.print(_format_coordination_summary(log, coord_entries))
    elif mode == "debug":
        console.print(_format_debug(log, entries))


@app.command("how")
def how_did_you_decide(
    query: str = typer.Argument(..., help="What to explain (e.g., 'routing', 'why escalate')"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w",
                                           help="Search in specific workspace"),
):
    """
    Ask how a specific decision was made across workspaces.
    
    Examples:
        nanobot how "why did you choose Claude"
        nanobot how "what memories did you use"
        nanobot how "why did you escalate" -w #coordination-website
        nanobot how "what did @researcher find"
    """
    from nanobot.agent.work_log_manager import WorkspaceWorkLogManager
    
    manager = WorkspaceWorkLogManager()
    
    # Search across all workspace logs or specific one
    if workspace:
        logs = [manager.get_workspace_log(workspace)]
    else:
        logs = manager.get_all_logs(limit=10)
    
    # Search for relevant entries
    results = []
    for log in logs:
        for entry in log.entries:
            if query.lower() in entry.message.lower():
                results.append((log.workspace_id, entry))
    
    if not results:
        console.print(f"[yellow]No entries found matching '{query}'[/yellow]")
        return
    
    console.print(f"[cyan]Found {len(results)} relevant decisions:[/cyan]\n")
    for workspace_id, entry in results[:5]:  # Show top 5
        console.print(f"[bold]{workspace_id}[/bold] - Step {entry.step}")
        console.print(f"  {entry.bot_name}: {entry.message}")
        if entry.confidence:
            console.print(f"  Confidence: {entry.confidence:.0%}")
        console.print()


@app.command("workspace-logs")
def list_workspace_logs(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w",
                                           help="Filter by workspace"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of logs to show"),
):
    """
    List recent work logs across workspaces.
    
    Examples:
        nanobot workspace-logs              # Show all recent logs
        nanobot workspace-logs -w #general  # Show only #general logs
        nanobot workspace-logs -n 20        # Show last 20 logs
    """
    from nanobot.agent.work_log_manager import WorkspaceWorkLogManager
    
    manager = WorkspaceWorkLogManager()
    logs = manager.get_all_logs(limit=limit, workspace=workspace)
    
    if not logs:
        console.print("[yellow]No work logs found.[/yellow]")
        return
    
    table = Table(title="Recent Work Logs")
    table.add_column("Workspace", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Bots", style="yellow")
    table.add_column("Duration", style="dim")
    table.add_column("Status", style="blue")
    
    for log in logs:
        duration = "In Progress" if not log.end_time else f"{(log.end_time - log.start_time).seconds}s"
        status = "🟢 Complete" if log.end_time else "🟡 Active"
        
        table.add_row(
            log.workspace_id,
            log.workspace_type.value,
            ", ".join(log.participants[:3]),  # Show first 3 bots
            duration,
            status
        )
    
    console.print(table)
```

#### 3.2 Agent Integration
Add to system prompt:
```markdown
## Work Log Transparency

When asked "how did you decide" or "why did you choose":
1. Reference the work log for that interaction
2. Explain the reasoning chain
3. Show confidence levels
4. Admit uncertainty when present

Example:
User: "Why did you use that skill?"
You: "I scanned 5 available skills. 'github-manager' matched your request 
('push to repo') with 94% confidence based on tool patterns. 
Alternative 'git-cli' was 67% confident."
```

---

### Phase 4: Progressive UI (Week 4)
**Goal:** Implement progressive disclosure UI

#### 4.1 Response Formatting
```python
def format_response_with_log(self, result: str, log: WorkLog) -> str:
    """Format response with optional work log."""
    
    if self.config.work_logs.show_in_response:
        # Full log included
        return f"""
{result}

---

<details>
<summary>🔍 How I decided this</summary>

{log.get_formatted_log("detailed")}
</details>
"""
    else:
        # Just the result, with a hint
        return f"""{result}

💡 Tip: Use `nanobot explain` to see how I made this decision."""
```

#### 4.2 Interactive Mode
In chat interface:
```
User: Check my bookmarks
Agent: [Processes...]

📚 I found 12 bookmarks. Here's a summary:
- 5 about AI/ML
- 3 about productivity
- 4 uncategorized

[See how I decided →] [Ask follow-up →]

User clicks "See how I decided"
Agent shows work log with:
✓ Loaded x-bookmarks skill (verified)
✓ Executed bird CLI to fetch bookmarks  
⚠ 4 bookmarks without clear categories
✓ Categorized 8/12 with 91% confidence
```

---

## Technical Specifications

### Storage Options

#### Option A: SQLite (Recommended)
```sql
CREATE TABLE work_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    query TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    final_output TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE work_log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_log_id TEXT,
    step INTEGER,
    timestamp TIMESTAMP,
    level TEXT,
    category TEXT,
    message TEXT,
    details_json TEXT,
    confidence REAL,
    duration_ms INTEGER,
    FOREIGN KEY (work_log_id) REFERENCES work_logs(id)
);
```

**Pros:** Persistent, queryable, scalable  
**Cons:** Slight performance overhead

#### Option B: In-Memory
```python
work_logs: dict[str, WorkLog] = {}  # session_id -> WorkLog
```

**Pros:** Fast, no I/O  
**Cons:** Lost on restart, memory usage

#### Option C: JSON Files
```python
# workspace/.nanobot/work-logs/{session_id}.json
```

**Pros:** Human-readable, easy to inspect  
**Cons:** Slower queries, file system overhead

**Recommendation:** SQLite for production, in-memory for testing.

### Performance Considerations

1. **Async Logging:** Don't block agent loop
   ```python
   asyncio.create_task(self._async_log(...))
   ```

2. **Sampling:** Only log 10% of "info" level in production
   ```python
   if level == LogLevel.INFO and random.random() > 0.1:
       return  # Skip
   ```

3. **Truncation:** Limit large fields
   ```python
   details["result"] = str(result)[:500]  # Truncate
   ```

4. **Retention:** Auto-delete old logs
   ```python
   DELETE FROM work_logs WHERE created_at < date('now', '-30 days');
   ```

### Privacy & Security

1. **PII Masking:** Automatically redact sensitive data
   ```python
   message = mask_secrets(message)  # Use existing sanitizer
   ```

2. **Access Control:** Logs only accessible to workspace owner
   ```python
   # Check user_id matches session owner
   ```

3. **Opt-out:** Users can disable logging entirely
   ```json
   {"work_logs": {"enabled": false}}
   ```

---

## Testing Strategy

### Unit Tests
```python
def test_work_log_creation():
    log = WorkLog(session_id="test", query="hello")
    log.add_entry(LogLevel.INFO, "test", "message")
    assert len(log.entries) == 1

def test_low_confidence_flagging():
    log = WorkLog(session_id="test", query="hello")
    log.add_entry(LogLevel.DECISION, "routing", "test", confidence=0.5)
    # Should be flagged as uncertainty
    assert log.entries[0].level == LogLevel.UNCERTAINTY

def test_formatted_output():
    log = WorkLog(session_id="test", query="hello")
    log.add_entry(LogLevel.INFO, "test", "step 1")
    log.add_entry(LogLevel.DECISION, "test", "step 2")
    
    formatted = log.get_formatted_log("summary")
    assert "step 1" in formatted
    assert "step 2" in formatted
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_agent_loop_logging():
    agent = AgentLoop(..., work_logs_enabled=True)
    
    result = await agent.process("test message")
    
    # Verify log was created
    log = agent.work_log.current_log
    assert log is not None
    assert len(log.entries) > 0
    
    # Verify specific entries
    routing_entries = [e for e in log.entries if e.category == "routing"]
    assert len(routing_entries) > 0
```

---

## Rollout Plan - Multi-Agent Extensions

### ✅ Phase 1: Foundation (COMPLETE - See Single-Bot)
**Goal:** Build basic work log system
**Status:** ✅ **COMPLETE** - All single-bot features implemented

**Already Done:**
- ✅ WorkLog and WorkLogEntry data classes
- ✅ WorkLogManager with SQLite storage
- ✅ Configuration (WorkLogsConfig)
- ✅ 33 comprehensive tests
- See [WORK_LOGS_SINGLE_BOT.md](../WORK_LOGS_SINGLE_BOT.md)

### 🔄 Phase 1A: Multi-Agent Data Model Extensions
**Goal:** Add multi-agent fields to existing data model
**Status:** 🔄 **PENDING**

**Tasks:**
- [ ] Add HANDOFF, COORDINATION to LogLevel enum
- [ ] Add workspace_id, workspace_type, participants fields
- [ ] Add bot_name, bot_role, triggered_by fields
- [ ] Add mentions, response_to fields
- [ ] Add coordinator_mode, escalation flags
- [ ] Add shareable_insight, insight_category fields
- [ ] Add is_bot_conversation() method
- [ ] Update database schema (migration)
- [ ] Update tests for new fields

**Estimated Effort:** 2-3 hours

### 🔄 Phase 2: Multi-Agent Integration
**Goal:** Integrate with multi-agent orchestration
**Status:** 🔄 **PENDING**

**Prerequisites:** Workspace data model must exist

**Tasks:**
- [ ] Hook into Workspace lifecycle (requires Workspace model)
- [ ] Add bot-to-bot conversation logging
- [ ] Implement coordinator mode tracking
- [ ] Add escalation logging for autonomous decisions
- [ ] Test workspace types: open, project, direct, coordination
- [ ] Integration tests with multiple bots

**Estimated Effort:** 4-6 hours

### 🔄 Phase 3: Learning Exchange Pipeline
**Goal:** Connect work logs to Learning Exchange
**Status:** 🔄 **PENDING**

**Prerequisites:** Learning Exchange system must exist

**Tasks:**
- [ ] Implement `_queue_for_learning_exchange()`
- [ ] Add insight categorization (user_preference, tool_pattern, etc.)
- [ ] Test auto-sharing of high-confidence insights
- [ ] Verify workspace-scoped learning (general vs specific)
- [ ] Add manual approval workflow for sensitive insights

**Estimated Effort:** 3-4 hours

### 🔄 Phase 4: Enhanced CLI Commands
**Goal:** Multi-agent aware CLI commands
**Status:** 🔄 **PENDING**

**Already Done (Single-Bot):**
- ✅ `explain` command
- ✅ `how` command
- ✅ Interactive shortcuts

**New Multi-Agent Features:**
- [ ] Add `explain -w #workspace` command
- [ ] Add `workspace-logs` command
- [ ] Implement bot filtering (`-b @researcher`)
- [ ] Add coordination mode view (`--mode coordination`)
- [ ] Add work log query tools to agent (meta-cognition)

**Estimated Effort:** 2-3 hours

### ✅ Phase 5: Testing & Polish (COMPLETE - Single Bot)
**Goal:** Production-ready work logs
**Status:** ✅ **COMPLETE** - All single-bot testing done

**Already Done:**
- ✅ 33 comprehensive tests
- ✅ PII masking
- ✅ Performance optimization
- ✅ Production deployment

**New Multi-Agent Testing Needed:**
- [ ] Test workspace isolation
- [ ] Test bot-to-bot logging
- [ ] Test coordinator mode
- [ ] Test Learning Exchange integration

**Estimated Effort:** 3-4 hours

### Summary

**Total Multi-Agent Effort:** ~14-20 hours
- Phase 1A: 2-3 hours (data model)
- Phase 2: 4-6 hours (integration)
- Phase 3: 3-4 hours (Learning Exchange)
- Phase 4: 2-3 hours (CLI enhancements)
- Phase 5: 3-4 hours (multi-agent testing)

**Dependencies:**
- ✅ Work logs foundation (COMPLETE)
- 🔄 Workspace data model (Multi-Agent Architecture Phase 1)
- 🔄 Learning Exchange system (Multi-Agent Architecture Phase 3)

**Dependencies:**
- Requires Workspace data model (Multi-Agent Architecture Phase 1)
- Requires Learning Exchange system (Multi-Agent Architecture Phase 3)
- Can start in parallel with other multi-agent features

---

## Success Metrics

1. **Adoption:** % of users who run `nanobot explain` at least once
2. **Trust:** User survey - "I understand how nanobot makes decisions" (1-5)
3. **Debugging:** Average time to diagnose agent issues (before vs after)
4. **Error Detection:** # of errors caught by users reviewing work logs

Target: 80% of users report increased understanding after viewing work logs.

---

## Open Questions

1. Should work logs be shared between users (anonymized) for research?
2. How long should logs be retained by default?
3. Should we allow exporting work logs for debugging?
4. Should there be a "silent mode" for API calls that skips logging entirely?

---

## Integration Summary

### Work Logs + Multi-Agent Architecture

**Workspace-Centric Logging:**
- Work logs are scoped to workspaces (not global sessions)
- Each workspace (#general, #project-alpha) maintains its own log
- Logs respect workspace privacy boundaries

**Multi-Agent Collaboration Tracking:**
- Bot-to-bot conversations logged with @mentions
- Coordinator mode decisions tracked separately
- Escalations clearly marked for user attention

**Learning Exchange Pipeline:**
- High-confidence insights auto-queued for sharing
- Workspace-scoped learning (general vs specific)
- Cross-bot knowledge propagation

**CLI Integration:**
- `nanobot explain -w #workspace` - View workspace-specific logs
- `nanobot workspace-logs` - List logs across workspaces
- Workspace filtering and bot filtering supported

---

## Related Documentation

- [MULTI_AGENT_ORCHESTRATION_ANALYSIS.md](./MULTI_AGENT_ORCHESTRATION_ANALYSIS.md) - **Primary integration doc**
- [MEMORY_IMPLEMENTATION_STATUS.md](MEMORY_IMPLEMENTATION_STATUS.md) - Memory system architecture
- [Smart Routing Documentation](ROUTING.md) - Routing decision logic
- [Security Scanner](docs/SECURITY.md) - Skill verification (future doc)
- [VoxYZ Research](https://www.voxyz.space/insights/agent-work-logs-beat-polish-trust) - Original article

---

**Next Steps:**
1. ✅ Review this document with the team
2. ✅ Ensure alignment with Multi-Agent Architecture
3. Create GitHub issues for each phase
4. Prioritize workspace-aware WorkLogManager implementation
5. Integrate with Learning Exchange system
6. Add workspace-specific CLI commands
7. Schedule weekly check-ins during implementation
