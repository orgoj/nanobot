"""Tool output compaction to prevent context overflow.

This module provides intelligent management of tool outputs to prevent
large responses (like 396KB JSON files) from overwhelming the context
window and crashing the session.

Inspired by OpenClaw Issue #2254:
"Telegram sessions grow to 2-3MB within hours... Sessions hit 208,467 tokens
(exceeding the 200k model limit), auto-compaction fails, and every subsequent
message fails silently."

Solution:
- Store full tool outputs in SQLite
- Keep truncated/summarized version in context
- Provide reference-based access to full output
- Emergency truncation at 95% threshold
"""

import uuid
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger


@dataclass
class ToolOutputEntry:
    """Represents a stored tool output."""
    id: str
    tool_name: str
    full_output: str
    context_summary: str
    created_at: datetime
    session_key: str
    accessed_count: int = 0
    char_count: int = 0
    truncated_in_context: bool = False


class ToolOutputStore:
    """
    Stores full tool outputs in SQLite for reference-based access.
    
    This prevents large outputs (e.g., 396KB JSON) from consuming context
    tokens while still making them available when needed.
    """
    
    def __init__(self, memory_store):
        """
        Initialize the tool output store.
        
        Args:
            memory_store: MemoryStore instance for SQLite operations.
        """
        self.memory_store = memory_store
        self._init_table()
    
    def _init_table(self):
        """Create tool_outputs table if it doesn't exist."""
        conn = self.memory_store._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_outputs (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                full_output TEXT NOT NULL,
                context_summary TEXT,
                created_at REAL NOT NULL,
                session_key TEXT,
                accessed_count INTEGER DEFAULT 0,
                char_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_outputs_session ON tool_outputs(session_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_outputs_created ON tool_outputs(created_at)")
    
    def store_output(
        self,
        tool_name: str,
        full_output: str,
        context_summary: str,
        session_key: str = ""
    ) -> str:
        """
        Store a tool output and return its reference ID.
        
        Args:
            tool_name: Name of the tool.
            full_output: The complete output.
            context_summary: A shortened version for context.
            session_key: Session identifier.
        
        Returns:
            Reference ID for the stored output.
        """
        output_id = str(uuid.uuid4())
        
        conn = self.memory_store._get_connection()
        conn.execute("""
            INSERT INTO tool_outputs (id, tool_name, full_output, context_summary, 
                                     created_at, session_key, char_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            output_id,
            tool_name,
            full_output,
            context_summary,
            datetime.now().timestamp(),
            session_key,
            len(full_output)
        ))
        conn.commit()
        
        logger.debug(f"Stored tool output {output_id} ({len(full_output)} chars) for {tool_name}")
        
        return output_id
    
    def get_output(self, output_id: str) -> ToolOutputEntry | None:
        """
        Retrieve a stored tool output.
        
        Args:
            output_id: The reference ID.
        
        Returns:
            ToolOutputEntry or None if not found.
        """
        conn = self.memory_store._get_connection()
        row = conn.execute(
            "SELECT * FROM tool_outputs WHERE id = ?",
            (output_id,)
        ).fetchone()
        
        if not row:
            return None
        
        # Increment access count
        conn.execute(
            "UPDATE tool_outputs SET accessed_count = accessed_count + 1 WHERE id = ?",
            (output_id,)
        )
        conn.commit()
        
        return ToolOutputEntry(
            id=row["id"],
            tool_name=row["tool_name"],
            full_output=row["full_output"],
            context_summary=row["context_summary"],
            created_at=datetime.fromtimestamp(row["created_at"]),
            session_key=row["session_key"],
            accessed_count=row["accessed_count"] + 1,
            char_count=row["char_count"]
        )
    
    def cleanup_old_outputs(self, max_age_hours: int = 24) -> int:
        """
        Remove old tool outputs to save space.
        
        Args:
            max_age_hours: Delete outputs older than this.
        
        Returns:
            Number of outputs deleted.
        """
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        
        conn = self.memory_store._get_connection()
        cursor = conn.execute(
            "DELETE FROM tool_outputs WHERE created_at < ?",
            (cutoff,)
        )
        conn.commit()
        
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old tool outputs")
        
        return deleted


class ToolOutputCompactor:
    """
    Compacts tool outputs to prevent context overflow.
    
    Automatically truncates large outputs and stores full versions
    in SQLite for reference-based access.
    
    Key features:
    - Automatic truncation at 2000 chars (configurable)
    - Full output stored in SQLite
    - Reference-based access (ref://output_id)
    - Smart summarization for large outputs
    - Redundant call detection and collapse
    """
    
    def __init__(
        self,
        memory_store,
        max_context_chars: int = 2000,
        summarize_threshold: int = 5000,
        store_full_output: bool = True
    ):
        """
        Initialize the tool output compactor.
        
        Args:
            memory_store: MemoryStore for output storage.
            max_context_chars: Maximum characters to keep in context.
            summarize_threshold: Summarize if output exceeds this.
            store_full_output: Whether to store full output in SQLite.
        """
        self.max_context_chars = max_context_chars
        self.summarize_threshold = summarize_threshold
        self.store_full_output = store_full_output
        
        if store_full_output and memory_store:
            self.output_store = ToolOutputStore(memory_store)
        else:
            self.output_store = None
    
    def process_tool_result(
        self,
        tool_name: str,
        result: str,
        session_key: str = ""
        max_context_chars: int | None = None
    ) -> dict[str, Any]:
        """
        Process a tool result for context storage.
        
        Args:
            tool_name: Name of the tool.
            result: The tool output.
            session_key: Session identifier.
            max_context_chars: Override max chars (uses default if None).
        
        Returns:
            Dict with:
            - context_version: Truncated version for context
            - full_output_id: Reference to full output (if stored)
            - truncated: Whether truncation occurred
            - summary: Summary text (if summarized)
        """
        max_chars = max_context_chars or self.max_context_chars
        
        # If result is small enough, keep it as-is
        if len(result) <= max_chars:
            return {
                "context_version": result,
                "full_output_id": None,
                "truncated": False,
                "summary": None
            }
        
        # Large output - need to compact
        logger.debug(f"Tool output too large ({len(result)} chars), compacting for {tool_name}")
        
        # Store full output if enabled
        full_output_id = None
        if self.output_store and self.store_full_output:
            # Create summary for storage
            summary = self._create_summary(result)
            full_output_id = self.output_store.store_output(
                tool_name=tool_name,
                full_output=result,
                context_summary=summary,
                session_key=session_key
            )
        
        # Create context version
        if len(result) > self.summarize_threshold:
            # Summarize instead of truncate
            context_version = self._create_summary(result, max_chars)
        else:
            # Truncate with notice
            context_version = result[:max_chars] + f"\n...[truncated {len(result) - max_chars} chars]"
        
        # Add reference if stored
        if full_output_id:
            context_version += f"\n[Full output: ref://{full_output_id}]"
        
        return {
            "context_version": context_version,
            "full_output_id": full_output_id,
            "truncated": True,
            "summary": None if len(result) <= self.summarize_threshold else context_version
        }
    
    def _create_summary(self, text: str, max_chars: int = 500) -> str:
        """
        Create a summary of large text.
        
        For now, simple truncation with key info extraction.
        In production, this could use LLM summarization.
        
        Args:
            text: Text to summarize.
            max_chars: Maximum characters for summary.
        
        Returns:
            Summary text.
        """
        # Extract key information
        lines = text.split('\n')
        
        # Try to find important lines (headers, counts, errors)
        important_lines = []
        for line in lines[:50]:  # Check first 50 lines
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                # Look for lines with numbers, key indicators
                if any(indicator in stripped.lower() for indicator in 
                       ['total:', 'count:', 'error:', 'found:', 'result:', 'success', 'failed']):
                    important_lines.append(stripped)
        
        # Create summary
        summary_parts = [f"Output ({len(text)} chars, {len(lines)} lines)"]
        
        if important_lines:
            summary_parts.append("Key points:")
            for line in important_lines[:5]:  # Top 5 important lines
                summary_parts.append(f"  • {line[:80]}{'...' if len(line) > 80 else ''}")
        
        summary = '\n'.join(summary_parts)
        
        # Ensure within limit
        if len(summary) > max_chars:
            summary = summary[:max_chars-3] + "..."
        
        return summary
    
    def compact_session_tool_outputs(
        self,
        messages: list[dict[str, Any]],
        session_key: str = ""
    ) -> list[dict[str, Any]]:
        """
        Compact tool outputs in a session's messages.
        
        Processes all tool_result messages and compacts large outputs.
        
        Args:
            messages: Session messages.
            session_key: Session identifier.
        
        Returns:
            Messages with compacted tool outputs.
        """
        compacted = []
        
        for msg in messages:
            if msg.get("role") == "tool" or self._is_tool_result(msg):
                # Extract tool result content
                content = msg.get("content", "")
                tool_name = msg.get("name", "unknown")
                
                if len(content) > self.max_context_chars:
                    # Compact this tool output
                    result = self.process_tool_result(
                        tool_name=tool_name,
                        result=content,
                        session_key=session_key
                    )
                    
                    # Update message with compacted version
                    msg_copy = msg.copy()
                    msg_copy["content"] = result["context_version"]
                    msg_copy["_full_output_id"] = result["full_output_id"]
                    msg_copy["_truncated"] = result["truncated"]
                    compacted.append(msg_copy)
                else:
                    compacted.append(msg)
            else:
                compacted.append(msg)
        
        return compacted
    
    def _is_tool_result(self, message: dict[str, Any]) -> bool:
        """Check if a message is a tool result."""
        content = message.get("content", [])
        
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return True
        
        return message.get("role") == "tool"
    
    def detect_redundant_calls(
        self,
        messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Detect and collapse redundant tool calls.
        
        If the same tool is called multiple times consecutively with
        identical arguments, collapse into a single entry.
        
        Args:
            messages: Messages to process.
        
        Returns:
            Messages with redundant calls collapsed.
        """
        if not messages:
            return messages
        
        result = []
        prev_tool_hash = None
        prev_tool_count = 1
        
        for msg in messages:
            if msg.get("role") == "assistant":
                # Check for tool_use blocks
                content = msg.get("content", [])
                if isinstance(content, list):
                    tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
                    
                    if tool_uses:
                        # Create hash of tool calls
                        tool_hash = self._hash_tool_calls(tool_uses)
                        
                        if tool_hash == prev_tool_hash:
                            # Same as previous, increment count
                            prev_tool_count += 1
                            # Skip adding this message (will merge later)
                            continue
                        else:
                            # Different tool, add previous with count if needed
                            if prev_tool_count > 1 and result:
                                # Add note about collapsed calls
                                last_msg = result[-1]
                                if last_msg.get("role") == "assistant":
                                    last_content = last_msg.get("content", [])
                                    if isinstance(last_content, list):
                                        # Add collapsed note to text block
                                        text_blocks = [b for b in last_content if b.get("type") == "text"]
                                        if text_blocks:
                                            text_blocks[0]["text"] += f"\n[Repeated {prev_tool_count} times]"
                            
                            prev_tool_hash = tool_hash
                            prev_tool_count = 1
            
            result.append(msg)
        
        return result
    
    def _hash_tool_calls(self, tool_uses: list[dict]) -> str:
        """Create a hash of tool calls for redundancy detection."""
        tool_str = "|".join([
            f"{t.get('name', '')}:{str(t.get('input', {}))}"
            for t in tool_uses
        ])
        return hashlib.md5(tool_str.encode()).hexdigest()[:16]


# Convenience function

def compact_tool_outputs(
    messages: list[dict[str, Any]],
    memory_store,
    max_context_chars: int = 2000,
    session_key: str = ""
) -> list[dict[str, Any]]:
    """
    Convenience function to compact tool outputs in messages.
    
    Args:
        messages: Messages to process.
        memory_store: MemoryStore for output storage.
        max_context_chars: Maximum chars to keep in context.
        session_key: Session identifier.
    
    Returns:
        Messages with compacted tool outputs.
    """
    compactor = ToolOutputCompactor(
        memory_store=memory_store,
        max_context_chars=max_context_chars
    )
    
    return compactor.compact_session_tool_outputs(messages, session_key)
