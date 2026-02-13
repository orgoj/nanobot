"""Work log data models for tracking AI agent decision-making.

This module provides data structures for logging agent work, including
decisions, tool executions, errors, and other key events.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum
import json


class LogLevel(Enum):
    """Severity/importance levels for work log entries."""
    INFO = "info"           # Normal operation
    THINKING = "thinking"   # Reasoning steps
    DECISION = "decision"   # Choice made
    CORRECTION = "correction"  # Mistake fixed
    UNCERTAINTY = "uncertainty"  # Low confidence
    WARNING = "warning"     # Issue encountered
    ERROR = "error"         # Failure
    TOOL = "tool"           # Tool execution


@dataclass
class WorkLogEntry:
    """A single entry in a work log.
    
    Represents one step in the agent's decision-making process,
    such as a thought, decision, tool execution, or error.
    """
    timestamp: datetime
    level: LogLevel
    step: int                    # Sequential step number
    category: str                # "memory", "tool", "routing", etc.
    message: str                 # Human-readable description
    details: dict = field(default_factory=dict)  # Structured data
    confidence: Optional[float] = None  # 0.0-1.0 for uncertainty
    duration_ms: Optional[int] = None   # How long this step took
    
    # Tool execution fields
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[Any] = None
    tool_status: Optional[str] = None   # "success", "error", "timeout"
    tool_error: Optional[str] = None
    
    def is_tool_entry(self) -> bool:
        """Check if this entry represents a tool execution."""
        return self.tool_name is not None
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "step": self.step,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "tool_status": self.tool_status,
            "tool_error": self.tool_error
        }


@dataclass
class WorkLog:
    """A complete work log for a single session.
    
    Tracks all the steps an agent took to process a user query,
    from start to finish.
    """
    session_id: str
    query: str                   # Original user query
    start_time: datetime
    end_time: Optional[datetime] = None
    entries: list[WorkLogEntry] = field(default_factory=list)
    final_output: Optional[str] = None
    
    def add_entry(self, level: LogLevel, category: str, message: str,
                  details: dict = None, confidence: float = None,
                  duration_ms: int = None) -> WorkLogEntry:
        """Add a work log entry.
        
        Args:
            level: Severity/importance of the entry
            category: Type of activity (memory, tool, routing, etc.)
            message: Human-readable description
            details: Structured data about the entry
            confidence: Confidence level (0.0-1.0) if applicable
            duration_ms: How long this step took in milliseconds
            
        Returns:
            The created WorkLogEntry
        """
        entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=level,
            step=len(self.entries) + 1,
            category=category,
            message=message,
            details=details or {},
            confidence=confidence,
            duration_ms=duration_ms
        )
        self.entries.append(entry)
        return entry
    
    def add_tool_entry(self, tool_name: str, tool_input: dict,
                      tool_output: Any, tool_status: str,
                      duration_ms: int, message: str = None) -> WorkLogEntry:
        """Add a tool execution entry.
        
        Args:
            tool_name: Name of the tool that was executed
            tool_input: Input parameters to the tool
            tool_output: Result from the tool
            tool_status: Execution status ("success", "error", etc.)
            duration_ms: How long the tool took to execute
            message: Optional custom message (defaults to tool name)
            
        Returns:
            The created WorkLogEntry
        """
        entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.TOOL,
            step=len(self.entries) + 1,
            category="tool_execution",
            message=message or f"Executed {tool_name}",
            duration_ms=duration_ms,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            tool_status=tool_status
        )
        self.entries.append(entry)
        return entry
    
    def get_entries_by_level(self, level: LogLevel) -> list[WorkLogEntry]:
        """Get all entries of a specific level.
        
        Args:
            level: The log level to filter by
            
        Returns:
            List of matching entries
        """
        return [e for e in self.entries if e.level == level]
    
    def get_entries_by_category(self, category: str) -> list[WorkLogEntry]:
        """Get all entries of a specific category.
        
        Args:
            category: The category to filter by
            
        Returns:
            List of matching entries
        """
        return [e for e in self.entries if e.category == category]
    
    def get_errors(self) -> list[WorkLogEntry]:
        """Get all error entries.
        
        Returns:
            List of error entries
        """
        return self.get_entries_by_level(LogLevel.ERROR)
    
    def get_decisions(self) -> list[WorkLogEntry]:
        """Get all decision entries.
        
        Returns:
            List of decision entries
        """
        return self.get_entries_by_level(LogLevel.DECISION)
    
    def get_tool_calls(self) -> list[WorkLogEntry]:
        """Get all tool execution entries.
        
        Returns:
            List of tool execution entries
        """
        return [e for e in self.entries if e.is_tool_entry()]
    
    def get_duration_ms(self) -> Optional[int]:
        """Get total duration of the session in milliseconds.
        
        Returns:
            Duration in milliseconds, or None if session hasn't ended
        """
        if not self.end_time:
            return None
        return int((self.end_time - self.start_time).total_seconds() * 1000)
    
    def to_dict(self) -> dict:
        """Convert work log to dictionary for serialization.
        
        Returns:
            Dictionary representation of the work log
        """
        return {
            "session_id": self.session_id,
            "query": self.query,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "final_output": self.final_output,
            "entry_count": len(self.entries),
            "duration_ms": self.get_duration_ms(),
            "entries": [e.to_dict() for e in self.entries]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert work log to JSON string.
        
        Args:
            indent: JSON indentation level
            
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)
