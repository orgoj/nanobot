"""Tests for the work logs system."""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from nanobot.agent.work_log import WorkLog, WorkLogEntry, LogLevel
from nanobot.agent.work_log_manager import WorkLogManager, get_work_log_manager, reset_work_log_manager


class TestLogLevel:
    """Test LogLevel enum."""
    
    def test_log_level_values(self):
        """Test that all log levels have correct values."""
        assert LogLevel.INFO.value == "info"
        assert LogLevel.THINKING.value == "thinking"
        assert LogLevel.DECISION.value == "decision"
        assert LogLevel.CORRECTION.value == "correction"
        assert LogLevel.UNCERTAINTY.value == "uncertainty"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.TOOL.value == "tool"


class TestWorkLogEntry:
    """Test WorkLogEntry dataclass."""
    
    def test_create_basic_entry(self):
        """Test creating a basic work log entry."""
        entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            step=1,
            category="test",
            message="Test message"
        )
        
        assert entry.step == 1
        assert entry.level == LogLevel.INFO
        assert entry.category == "test"
        assert entry.message == "Test message"
        assert entry.details == {}
        assert entry.confidence is None
        assert entry.duration_ms is None
    
    def test_create_entry_with_details(self):
        """Test creating entry with details and confidence."""
        entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.DECISION,
            step=2,
            category="routing",
            message="Classified as medium tier",
            details={"tier": "medium", "model": "gpt-4"},
            confidence=0.95,
            duration_ms=150
        )
        
        assert entry.confidence == 0.95
        assert entry.duration_ms == 150
        assert entry.details["tier"] == "medium"
    
    def test_is_tool_entry(self):
        """Test detecting tool entries."""
        regular_entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            step=1,
            category="general",
            message="Test"
        )
        
        tool_entry = WorkLogEntry(
            timestamp=datetime.now(),
            level=LogLevel.TOOL,
            step=2,
            category="tool_execution",
            message="Executed web_search",
            tool_name="web_search",
            tool_input={"query": "test"},
            tool_output={"results": []},
            tool_status="success"
        )
        
        assert not regular_entry.is_tool_entry()
        assert tool_entry.is_tool_entry()
    
    def test_to_dict(self):
        """Test serialization to dict."""
        entry = WorkLogEntry(
            timestamp=datetime(2026, 2, 12, 10, 30, 0),
            level=LogLevel.DECISION,
            step=1,
            category="routing",
            message="Test",
            confidence=0.85
        )
        
        data = entry.to_dict()
        
        assert data["step"] == 1
        assert data["level"] == "decision"
        assert data["confidence"] == 0.85
        assert "timestamp" in data


class TestWorkLog:
    """Test WorkLog dataclass."""
    
    def test_create_work_log(self):
        """Test creating a work log."""
        log = WorkLog(
            session_id="test-session",
            query="Hello world",
            start_time=datetime.now()
        )
        
        assert log.session_id == "test-session"
        assert log.query == "Hello world"
        assert log.entries == []
        assert log.end_time is None
    
    def test_add_entry(self):
        """Test adding entries to work log."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        entry1 = log.add_entry(
            level=LogLevel.INFO,
            category="general",
            message="First entry"
        )
        
        entry2 = log.add_entry(
            level=LogLevel.DECISION,
            category="routing",
            message="Second entry",
            confidence=0.9
        )
        
        assert len(log.entries) == 2
        assert entry1.step == 1
        assert entry2.step == 2
        assert log.entries[0].message == "First entry"
        assert log.entries[1].message == "Second entry"
    
    def test_add_tool_entry(self):
        """Test adding tool entries."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        entry = log.add_tool_entry(
            tool_name="web_search",
            tool_input={"query": "test"},
            tool_output={"results": ["a", "b"]},
            tool_status="success",
            duration_ms=250
        )
        
        assert entry.is_tool_entry()
        assert entry.tool_name == "web_search"
        assert entry.level == LogLevel.TOOL
        assert entry.duration_ms == 250
    
    def test_get_entries_by_level(self):
        """Test filtering entries by level."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "test", "Info message")
        log.add_entry(LogLevel.ERROR, "test", "Error message")
        log.add_entry(LogLevel.INFO, "test", "Another info")
        
        info_entries = log.get_entries_by_level(LogLevel.INFO)
        error_entries = log.get_entries_by_level(LogLevel.ERROR)
        
        assert len(info_entries) == 2
        assert len(error_entries) == 1
    
    def test_get_entries_by_category(self):
        """Test filtering entries by category."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "routing", "Routing info")
        log.add_entry(LogLevel.INFO, "memory", "Memory info")
        log.add_entry(LogLevel.INFO, "routing", "More routing")
        
        routing_entries = log.get_entries_by_category("routing")
        
        assert len(routing_entries) == 2
    
    def test_get_errors(self):
        """Test getting error entries."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "test", "Info")
        log.add_entry(LogLevel.ERROR, "test", "Error 1")
        log.add_entry(LogLevel.ERROR, "test", "Error 2")
        
        errors = log.get_errors()
        
        assert len(errors) == 2
        assert all(e.level == LogLevel.ERROR for e in errors)
    
    def test_get_decisions(self):
        """Test getting decision entries."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "test", "Info")
        log.add_entry(LogLevel.DECISION, "routing", "Decision 1")
        log.add_entry(LogLevel.DECISION, "memory", "Decision 2")
        
        decisions = log.get_decisions()
        
        assert len(decisions) == 2
    
    def test_get_tool_calls(self):
        """Test getting tool call entries."""
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "test", "Info")
        log.add_tool_entry("tool1", {}, "result", "success", 100)
        log.add_tool_entry("tool2", {}, "result", "success", 200)
        
        tools = log.get_tool_calls()
        
        assert len(tools) == 2
    
    def test_get_duration_ms(self):
        """Test calculating duration."""
        start = datetime.now()
        log = WorkLog(
            session_id="test",
            query="test",
            start_time=start
        )
        
        # Should be None while in progress
        assert log.get_duration_ms() is None
        
        # Set end time
        from datetime import timedelta
        log.end_time = start + timedelta(seconds=5)
        
        duration = log.get_duration_ms()
        assert duration is not None
        assert 4000 <= duration <= 6000  # Approximately 5 seconds
    
    def test_to_json(self):
        """Test JSON serialization."""
        log = WorkLog(
            session_id="test-session",
            query="test query",
            start_time=datetime.now()
        )
        
        log.add_entry(LogLevel.INFO, "test", "Test")
        log.end_time = datetime.now()
        log.final_output = "Test output"
        
        json_str = log.to_json()
        
        assert "test-session" in json_str
        assert "test query" in json_str
        assert "Test output" in json_str


class TestWorkLogManager:
    """Test WorkLogManager functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_work_logs.db"
            yield db_path
    
    @pytest.fixture
    def manager(self, temp_db):
        """Create a WorkLogManager with temp database."""
        reset_work_log_manager()
        mgr = WorkLogManager()
        mgr.db_path = temp_db
        mgr._init_db()
        return mgr
    
    def test_start_session(self, manager):
        """Test starting a work log session."""
        log = manager.start_session("test-session", "Test query")
        
        assert log.session_id == "test-session"
        assert log.query == "Test query"
        assert manager.current_log is not None
    
    def test_log_entry(self, manager):
        """Test logging an entry."""
        manager.start_session("test", "test")
        
        entry = manager.log(
            level=LogLevel.INFO,
            category="test",
            message="Test message"
        )
        
        assert entry is not None
        assert entry.step == 1
        assert len(manager.current_log.entries) == 1
    
    def test_log_tool(self, manager):
        """Test logging a tool execution."""
        manager.start_session("test", "test")
        
        entry = manager.log_tool(
            tool_name="web_search",
            tool_input={"query": "test"},
            tool_output={"results": []},
            tool_status="success",
            duration_ms=100
        )
        
        assert entry is not None
        assert entry.tool_name == "web_search"
        assert entry.tool_status == "success"
    
    def test_end_session(self, manager):
        """Test ending a work log session."""
        manager.start_session("test", "test")
        manager.log(LogLevel.INFO, "test", "Test")
        
        manager.end_session("Final output")
        
        assert manager.current_log is None
    
    def test_get_last_log(self, manager):
        """Test retrieving the last log."""
        # Create and end a session
        manager.start_session("session-1", "Query 1")
        manager.log(LogLevel.INFO, "test", "Entry 1")
        manager.end_session("Output 1")
        
        # Create another session
        manager.start_session("session-2", "Query 2")
        manager.log(LogLevel.INFO, "test", "Entry 2")
        manager.end_session("Output 2")
        
        # Get last log
        last_log = manager.get_last_log()
        
        assert last_log is not None
        assert last_log.session_id == "session-2"
        assert len(last_log.entries) == 1
    
    def test_get_log_by_session(self, manager):
        """Test retrieving a specific session."""
        manager.start_session("specific-session", "Specific query")
        manager.log(LogLevel.INFO, "test", "Test entry")
        manager.end_session("Test output")
        
        log = manager.get_log_by_session("specific-session")
        
        assert log is not None
        assert log.session_id == "specific-session"
        assert log.query == "Specific query"
    
    def test_get_formatted_log_summary(self, manager):
        """Test getting formatted summary."""
        manager.start_session("test", "Test query")
        manager.log(LogLevel.DECISION, "routing", "Classified as medium tier")
        manager.log_tool("web_search", {}, {"results": []}, "success", 150)
        manager.end_session("Test output")
        
        formatted = manager.get_formatted_log("summary")
        
        assert "Work Log Summary" in formatted
        assert "Test query" in formatted
        assert "medium tier" in formatted
    
    def test_get_formatted_log_detailed(self, manager):
        """Test getting detailed formatted log."""
        manager.start_session("test", "Test query")
        manager.log(LogLevel.INFO, "test", "Test entry")
        manager.end_session("Output")
        
        formatted = manager.get_formatted_log("detailed")
        
        assert "Detailed Work Log" in formatted
        assert "test" in formatted.lower()
    
    def test_disabled_logging(self, manager):
        """Test that disabled manager doesn't log."""
        disabled_manager = WorkLogManager(enabled=False)
        
        log = disabled_manager.start_session("test", "test")
        entry = disabled_manager.log(LogLevel.INFO, "test", "Test")
        
        # Should return dummy log but not save
        assert log is not None
        assert entry is None
    
    def test_multiple_sessions(self, manager):
        """Test handling multiple sessions."""
        for i in range(3):
            manager.start_session(f"session-{i}", f"Query {i}")
            manager.log(LogLevel.INFO, "test", f"Entry {i}")
            manager.end_session(f"Output {i}")
        
        # Get last should be session-2
        last = manager.get_last_log()
        assert last.session_id == "session-2"
    
    def test_log_persistence(self, manager):
        """Test that logs persist to database."""
        # Create first manager and log
        manager.start_session("persist-test", "Persist query")
        manager.log(LogLevel.INFO, "test", "Persist entry")
        manager.end_session("Persist output")
        
        # Create new manager instance (simulating restart)
        reset_work_log_manager()
        new_manager = WorkLogManager()
        new_manager.db_path = manager.db_path
        
        # Should retrieve the log
        log = new_manager.get_log_by_session("persist-test")
        
        assert log is not None
        assert log.query == "Persist query"
        assert len(log.entries) == 1


class TestWorkLogManagerFormatting:
    """Test WorkLogManager formatting functions."""
    
    @pytest.fixture
    def populated_manager(self):
        """Create a manager with a populated log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            reset_work_log_manager()
            mgr = WorkLogManager()
            mgr.db_path = db_path
            mgr._init_db()
            
            mgr.start_session("test", "Test query about Python programming")
            mgr.log(LogLevel.INFO, "general", "Processing user message")
            mgr.log(
                LogLevel.DECISION,
                "routing",
                "Classified as medium tier",
                details={"tier": "medium", "model": "gpt-4"},
                confidence=0.92,
                duration_ms=150
            )
            mgr.log(
                LogLevel.TOOL,
                "memory",
                "Retrieved 450 characters of memory context",
                duration_ms=80
            )
            mgr.log_tool(
                "web_search",
                {"query": "Python best practices"},
                {"results": ["PEP 8", "Clean Code"]},
                "success",
                230
            )
            mgr.log(
                LogLevel.WARNING,
                "general",
                "Low confidence on entity extraction",
                confidence=0.45
            )
            mgr.end_session("Here's what I found about Python...")
            
            yield mgr
    
    def test_summary_format(self, populated_manager):
        """Test summary format includes key decisions."""
        formatted = populated_manager.get_formatted_log("summary")
        
        assert "Work Log Summary" in formatted
        assert "Python programming" in formatted
        assert "medium tier" in formatted
        assert "web_search" in formatted
    
    def test_detailed_format(self, populated_manager):
        """Test detailed format includes all information."""
        formatted = populated_manager.get_formatted_log("detailed")
        
        assert "Detailed Work Log" in formatted
        assert "DECISION" in formatted
        assert "92%" in formatted or "0.92" in formatted
        assert "150ms" in formatted
    
    def test_debug_format(self, populated_manager):
        """Test debug format is valid JSON."""
        import json
        
        formatted = populated_manager.get_formatted_log("debug")
        
        # Should be valid JSON
        data = json.loads(formatted)
        assert "session_id" in data
        assert "entries" in data
        assert len(data["entries"]) == 5


class TestWorkLogIntegration:
    """Integration tests for work logs with other components."""
    
    @pytest.fixture
    def temp_manager(self):
        """Create a temporary manager for integration tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "integration.db"
            reset_work_log_manager()
            mgr = WorkLogManager()
            mgr.db_path = db_path
            mgr._init_db()
            yield mgr
            reset_work_log_manager()
    
    def test_full_session_lifecycle(self, temp_manager):
        """Test a complete session from start to finish."""
        # Start session
        log = temp_manager.start_session(
            "cli:test-session",
            "What's the weather in Tokyo?"
        )
        
        # Log routing decision
        temp_manager.log(
            LogLevel.DECISION,
            "routing",
            "Classified as simple tier",
            details={"tier": "simple", "model": "gpt-3.5"},
            confidence=0.95,
            duration_ms=120
        )
        
        # Log memory retrieval
        temp_manager.log(
            LogLevel.INFO,
            "memory",
            "No relevant memory found",
            duration_ms=50
        )
        
        # Log tool execution
        temp_manager.log_tool(
            "web_search",
            {"query": "Tokyo weather today"},
            {"temperature": "22°C", "condition": "sunny"},
            "success",
            340
        )
        
        # Log response
        temp_manager.log(
            LogLevel.INFO,
            "general",
            "Response generated successfully",
            details={"response_length": 150}
        )
        
        # End session
        temp_manager.end_session(
            "It's 22°C and sunny in Tokyo today!"
        )
        
        # Verify by retrieving
        retrieved = temp_manager.get_last_log()
        assert retrieved is not None
        assert retrieved.session_id == "cli:test-session"
        assert len(retrieved.entries) == 4
        assert "Tokyo" in retrieved.final_output
    
    def test_error_handling(self, temp_manager):
        """Test that errors don't break logging."""
        temp_manager.start_session("error-test", "Test")
        
        # Log an error
        temp_manager.log(
            LogLevel.ERROR,
            "tool_execution",
            "Tool web_search failed: Timeout",
            details={"error": "Timeout after 30s"}
        )
        
        temp_manager.end_session("Sorry, I encountered an error")
        
        # Should still be retrievable
        log = temp_manager.get_last_log()
        errors = log.get_errors()
        
        assert len(errors) == 1
        assert "Timeout" in errors[0].message


class TestGlobalWorkLogManager:
    """Test the global singleton work log manager."""
    
    def test_singleton_pattern(self):
        """Test that get_work_log_manager returns same instance."""
        reset_work_log_manager()
        
        mgr1 = get_work_log_manager()
        mgr2 = get_work_log_manager()
        
        assert mgr1 is mgr2
    
    def test_reset_creates_new_instance(self):
        """Test that reset creates a new instance."""
        mgr1 = get_work_log_manager()
        reset_work_log_manager()
        mgr2 = get_work_log_manager()
        
        assert mgr1 is not mgr2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
