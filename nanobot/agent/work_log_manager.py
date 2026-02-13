"""Work log manager for storing and retrieving agent work logs.

This module provides persistent storage and management of work logs
using SQLite, with support for querying, formatting, and retrieval.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from nanobot.agent.work_log import WorkLog, WorkLogEntry, LogLevel
from nanobot.config.loader import get_data_dir


class WorkLogManager:
    """Manages work logs for agent sessions.
    
    Provides persistent storage via SQLite, with support for creating,
    retrieving, and formatting work logs. Uses a singleton pattern for
the current active log.
    """
    
    def __init__(self, enabled: bool = True):
        """Initialize the work log manager.
        
        Args:
            enabled: Whether work logging is enabled
        """
        self.enabled = enabled
        self.current_log: Optional[WorkLog] = None
        self.db_path = get_data_dir() / "work_logs.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for work logs."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Create work_logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT UNIQUE,
                    query TEXT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    final_output TEXT,
                    entry_count INTEGER DEFAULT 0
                )
            """)
            
            # Create work_log_entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_log_entries (
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
                    tool_name TEXT,
                    tool_input_json TEXT,
                    tool_output_json TEXT,
                    tool_status TEXT,
                    FOREIGN KEY (work_log_id) REFERENCES work_logs(id)
                )
            """)
            
            # Create indexes for faster queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entries_work_log 
                ON work_log_entries(work_log_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_logs_session 
                ON work_logs(session_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_work_logs_time 
                ON work_logs(start_time DESC)
            """)
    
    def start_session(self, session_id: str, query: str) -> WorkLog:
        """Start a new work log session.
        
        Args:
            session_id: Unique identifier for this session
            query: The user's original query/message
            
        Returns:
            The created WorkLog instance
        """
        if not self.enabled:
            # Return a dummy log that doesn't store anything
            return WorkLog(session_id=session_id, query=query, start_time=datetime.now())
        
        self.current_log = WorkLog(
            session_id=session_id,
            query=query,
            start_time=datetime.now()
        )
        
        # Save to database
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO work_logs (id, session_id, query, start_time) VALUES (?, ?, ?, ?)",
                    (session_id, session_id, query, self.current_log.start_time.isoformat())
                )
        except sqlite3.IntegrityError:
            # Session already exists, update it
            pass
        
        return self.current_log
    
    def log(self, level: LogLevel, category: str, message: str,
            details: dict = None, confidence: float = None,
            duration_ms: int = None) -> Optional[WorkLogEntry]:
        """Add an entry to the current work log.
        
        Args:
            level: Severity/importance level
            category: Type of activity
            message: Human-readable description
            details: Structured data
            confidence: Confidence level (0.0-1.0)
            duration_ms: How long this step took
            
        Returns:
            The created WorkLogEntry, or None if logging disabled
        """
        if not self.enabled or not self.current_log:
            return None
        
        entry = self.current_log.add_entry(
            level=level, category=category, message=message,
            details=details, confidence=confidence, duration_ms=duration_ms
        )
        
        # Save to database
        self._save_entry(entry)
        return entry
    
    def log_tool(self, tool_name: str, tool_input: dict, tool_output: any,
                tool_status: str, duration_ms: int) -> Optional[WorkLogEntry]:
        """Log a tool execution.
        
        Args:
            tool_name: Name of the tool
            tool_input: Input parameters
            tool_output: Tool result
            tool_status: Execution status
            duration_ms: Execution time in milliseconds
            
        Returns:
            The created WorkLogEntry, or None if logging disabled
        """
        if not self.enabled or not self.current_log:
            return None
        
        entry = self.current_log.add_tool_entry(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            tool_status=tool_status,
            duration_ms=duration_ms
        )
        
        self._save_entry(entry)
        return entry
    
    def _save_entry(self, entry: WorkLogEntry):
        """Save an entry to the database.
        
        Args:
            entry: The WorkLogEntry to save
        """
        if not self.current_log:
            return
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT INTO work_log_entries 
                       (work_log_id, step, timestamp, level, category, message,
                        details_json, confidence, duration_ms, tool_name,
                        tool_input_json, tool_output_json, tool_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.current_log.session_id,
                        entry.step,
                        entry.timestamp.isoformat(),
                        entry.level.value,
                        entry.category,
                        entry.message,
                        json.dumps(entry.details) if entry.details else None,
                        entry.confidence,
                        entry.duration_ms,
                        entry.tool_name,
                        json.dumps(entry.tool_input) if entry.tool_input else None,
                        json.dumps(entry.tool_output, default=str) if entry.tool_output else None,
                        entry.tool_status
                    )
                )
        except Exception as e:
            # Log error but don't crash the agent
            print(f"Warning: Failed to save work log entry: {e}")
    
    def end_session(self, final_output: str):
        """End the current work log session.
        
        Args:
            final_output: The final response/output
        """
        if not self.enabled or not self.current_log:
            return
        
        self.current_log.end_time = datetime.now()
        self.current_log.final_output = final_output
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """UPDATE work_logs 
                       SET end_time = ?, final_output = ?, entry_count = ?
                       WHERE session_id = ?""",
                    (
                        self.current_log.end_time.isoformat(),
                        final_output,
                        len(self.current_log.entries),
                        self.current_log.session_id
                    )
                )
        except Exception as e:
            print(f"Warning: Failed to update work log: {e}")
        
        self.current_log = None
    
    def get_last_log(self) -> Optional[WorkLog]:
        """Get the most recent work log.
        
        Returns:
            The most recent WorkLog, or None if no logs exist
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM work_logs ORDER BY start_time DESC LIMIT 1"
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                return self._load_log_from_row(conn, row)
        except Exception as e:
            print(f"Warning: Failed to load work log: {e}")
            return None
    
    def get_log_by_session(self, session_id: str) -> Optional[WorkLog]:
        """Get a specific work log by session ID.
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            The WorkLog, or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM work_logs WHERE session_id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                return self._load_log_from_row(conn, row)
        except Exception as e:
            print(f"Warning: Failed to load work log: {e}")
            return None
    
    def _load_log_from_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> WorkLog:
        """Load a WorkLog and its entries from database rows.
        
        Args:
            conn: Database connection
            row: The work_logs row
            
        Returns:
            Populated WorkLog instance
        """
        log = WorkLog(
            session_id=row['session_id'],
            query=row['query'],
            start_time=datetime.fromisoformat(row['start_time']),
            end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
            final_output=row['final_output']
        )
        
        # Load entries
        entries_cursor = conn.execute(
            """SELECT * FROM work_log_entries 
               WHERE work_log_id = ? ORDER BY step""",
            (row['session_id'],)
        )
        
        for entry_row in entries_cursor:
            log.entries.append(WorkLogEntry(
                timestamp=datetime.fromisoformat(entry_row['timestamp']),
                level=LogLevel(entry_row['level']),
                step=entry_row['step'],
                category=entry_row['category'],
                message=entry_row['message'],
                details=json.loads(entry_row['details_json']) if entry_row['details_json'] else {},
                confidence=entry_row['confidence'],
                duration_ms=entry_row['duration_ms'],
                tool_name=entry_row['tool_name'],
                tool_input=json.loads(entry_row['tool_input_json']) if entry_row['tool_input_json'] else None,
                tool_output=json.loads(entry_row['tool_output_json']) if entry_row['tool_output_json'] else None,
                tool_status=entry_row['tool_status']
            ))
        
        return log
    
    def get_formatted_log(self, mode: str = "summary") -> str:
        """Get the current or last log formatted for display.
        
        Args:
            mode: Format mode - "summary", "detailed", or "debug"
            
        Returns:
            Formatted string representation
        """
        if self.current_log:
            log = self.current_log
        else:
            log = self.get_last_log()
        
        if not log:
            return "No work log available"
        
        if mode == "summary":
            return self._format_summary(log)
        elif mode == "detailed":
            return self._format_detailed(log)
        elif mode == "debug":
            return self._format_debug(log)
        else:
            return self._format_summary(log)
    
    def _format_summary(self, log: WorkLog) -> str:
        """Format work log as a high-level summary.
        
        Args:
            log: The work log to format
            
        Returns:
            Summary string
        """
        lines = [
            f"Work Log Summary",
            f"Query: {log.query[:80]}{'...' if len(log.query) > 80 else ''}",
            f"Steps: {len(log.entries)}",
            f"Duration: {self._format_duration(log)}",
            "",
            "Key Events:"
        ]
        
        # Show key decisions and tools
        for entry in log.entries:
            if entry.level in [LogLevel.DECISION, LogLevel.TOOL, LogLevel.ERROR]:
                icon = self._get_level_icon(entry.level)
                lines.append(f"  {icon} Step {entry.step}: {entry.message}")
        
        # Show errors if any
        errors = [e for e in log.entries if e.level == LogLevel.ERROR]
        if errors:
            lines.extend(["", "Errors:"])
            for error in errors:
                lines.append(f"  ❌ Step {error.step}: {error.message}")
        
        return "\n".join(lines)
    
    def _format_detailed(self, log: WorkLog) -> str:
        """Format work log with all details.
        
        Args:
            log: The work log to format
            
        Returns:
            Detailed string
        """
        lines = [
            f"Detailed Work Log",
            f"{'=' * 50}",
            f"Session: {log.session_id}",
            f"Query: {log.query}",
            f"Started: {log.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {self._format_duration(log)}",
            "",
            "Steps:",
            f"{'-' * 50}"
        ]
        
        for entry in log.entries:
            icon = self._get_level_icon(entry.level)
            lines.append(f"\n{icon} Step {entry.step} [{entry.level.value.upper()}]")
            lines.append(f"   Time: {entry.timestamp.strftime('%H:%M:%S')}")
            lines.append(f"   Category: {entry.category}")
            lines.append(f"   Message: {entry.message}")
            
            if entry.confidence:
                lines.append(f"   Confidence: {entry.confidence:.0%}")
            if entry.duration_ms:
                lines.append(f"   Duration: {entry.duration_ms}ms")
            if entry.tool_name:
                lines.append(f"   Tool: {entry.tool_name} ({entry.tool_status})")
        
        return "\n".join(lines)
    
    def _format_debug(self, log: WorkLog) -> str:
        """Format work log as JSON for debugging.
        
        Args:
            log: The work log to format
            
        Returns:
            JSON string
        """
        return log.to_json(indent=2)
    
    def _get_level_icon(self, level: LogLevel) -> str:
        """Get emoji icon for log level.
        
        Args:
            level: The log level
            
        Returns:
            Emoji string
        """
        icons = {
            LogLevel.INFO: "ℹ️",
            LogLevel.THINKING: "🧠",
            LogLevel.DECISION: "🎯",
            LogLevel.CORRECTION: "🔄",
            LogLevel.UNCERTAINTY: "❓",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
            LogLevel.TOOL: "🔧"
        }
        return icons.get(level, "•")
    
    def _format_duration(self, log: WorkLog) -> str:
        """Format duration nicely.
        
        Args:
            log: The work log
            
        Returns:
            Human-readable duration string
        """
        if not log.end_time:
            return "In progress"
        
        duration = (log.end_time - log.start_time).total_seconds()
        if duration < 60:
            return f"{duration:.1f}s"
        else:
            return f"{duration/60:.1f}m"
    
    def cleanup_old_logs(self, days: int = 30):
        """Delete work logs older than specified days.
        
        Args:
            days: Number of days to keep
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Delete old entries first (foreign key constraint)
                conn.execute("""
                    DELETE FROM work_log_entries 
                    WHERE work_log_id IN (
                        SELECT session_id FROM work_logs 
                        WHERE start_time < datetime('now', '-{} days')
                    )
                """.format(days))
                
                # Delete old logs
                conn.execute("""
                    DELETE FROM work_logs 
                    WHERE start_time < datetime('now', '-{} days')
                """.format(days))
        except Exception as e:
            print(f"Warning: Failed to cleanup old logs: {e}")


# Global singleton instance
_work_log_manager: Optional[WorkLogManager] = None


def get_work_log_manager() -> WorkLogManager:
    """Get or create the global work log manager instance.
    
    Returns:
        The global WorkLogManager instance
    """
    global _work_log_manager
    if _work_log_manager is None:
        _work_log_manager = WorkLogManager()
    return _work_log_manager


def reset_work_log_manager():
    """Reset the global work log manager (useful for testing)."""
    global _work_log_manager
    _work_log_manager = None
