"""Token counting for accurate context management.

This module provides accurate token counting using tiktoken,
replacing the unreliable character-based estimation.

Inspired by OpenClaw's production-hardened context management,
we need accurate token counting to:
1. Monitor context usage in real-time
2. Trigger compaction at 80% threshold (not 100%)
3. Show context=X% to users
4. Reserve buffer for model response
"""

from typing import Any

from loguru import logger


class TokenCounter:
    """
    Accurate token counting using tiktoken.
    
    Replaces the unreliable 4 chars ≈ 1 token estimation with
    actual token counting using OpenAI's tiktoken library.
    
    Supports multiple model encodings (cl100k_base for Claude/GPT-4).
    """
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        """
        Initialize the token counter.
        
        Args:
            encoding_name: The tiktoken encoding to use.
                          cl100k_base is used by Claude and GPT-4.
        """
        self.encoding_name = encoding_name
        self._encoding = None
        self._init_encoding()
    
    def _init_encoding(self):
        """Lazy-load the tiktoken encoding."""
        if self._encoding is None:
            try:
                import tiktoken
                self._encoding = tiktoken.get_encoding(self.encoding_name)
                logger.info(f"TokenCounter initialized with {self.encoding_name} encoding")
            except ImportError:
                logger.warning("tiktoken not installed, falling back to estimation")
                self._encoding = None
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Uses tiktoken for accurate counting, falls back to
        character estimation if tiktoken unavailable.
        
        Args:
            text: The text to count.
        
        Returns:
            Number of tokens.
        """
        if not text:
            return 0
        
        if self._encoding is not None:
            try:
                return len(self._encoding.encode(text))
            except Exception as e:
                logger.warning(f"Token counting failed: {e}, using estimation")
        
        # Fallback: character-based estimation (4 chars ≈ 1 token)
        # This is less accurate but works without tiktoken
        return len(text) // 4
    
    def count_message(self, message: dict[str, Any]) -> int:
        """
        Count tokens in a message dict.
        
        Handles both simple string content and structured content
        with tool_use/tool_result blocks.
        
        Args:
            message: Message dict with 'role' and 'content'.
        
        Returns:
            Number of tokens in the message.
        """
        role = message.get("role", "")
        content = message.get("content", "")
        
        # Start with role tokens (approximate)
        total = self.count_tokens(role) + 3  # +3 for formatting overhead
        
        if isinstance(content, str):
            total += self.count_tokens(content)
        elif isinstance(content, list):
            # Structured content (tool_use, tool_result blocks)
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        total += self.count_tokens(block.get("text", ""))
                    elif block_type == "tool_use":
                        # Count tool_use ID and input
                        total += self.count_tokens(block.get("id", ""))
                        total += self.count_tokens(str(block.get("input", "")))
                    elif block_type == "tool_result":
                        # Count tool_result content
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            total += self.count_tokens(result_content)
                        elif isinstance(result_content, list):
                            for item in result_content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    total += self.count_tokens(item.get("text", ""))
                    else:
                        # Unknown block type, count as string
                        total += self.count_tokens(str(block))
                else:
                    total += self.count_tokens(str(block))
        else:
            total += self.count_tokens(str(content))
        
        return total
    
    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """
        Count total tokens in a list of messages.
        
        Args:
            messages: List of message dicts.
        
        Returns:
            Total token count.
        """
        return sum(self.count_message(msg) for msg in messages)
    
    def estimate_context_usage(
        self,
        system_prompt: str,
        history: list[dict[str, Any]],
        current_message: str,
        max_tokens: int = 8000
    ) -> dict[str, Any]:
        """
        Estimate total context usage.
        
        Args:
            system_prompt: The system prompt.
            history: Session history messages.
            current_message: Current user message.
            max_tokens: Maximum context window size.
        
        Returns:
            Dict with usage statistics:
            {
                'total_tokens': int,
                'percentage': float (0.0 - 1.0),
                'by_section': {
                    'system': int,
                    'history': int,
                    'current': int
                },
                'tokens_remaining': int
            }
        """
        system_tokens = self.count_tokens(system_prompt)
        history_tokens = self.count_messages(history)
        current_tokens = self.count_tokens(current_message)
        
        total = system_tokens + history_tokens + current_tokens
        
        return {
            'total_tokens': total,
            'percentage': total / max_tokens if max_tokens > 0 else 0.0,
            'by_section': {
                'system': system_tokens,
                'history': history_tokens,
                'current': current_tokens
            },
            'tokens_remaining': max(0, max_tokens - total)
        }
    
    def should_compact(self, current_tokens: int, max_tokens: int, threshold: float = 0.8) -> bool:
        """
        Check if compaction should trigger.
        
        Uses proactive threshold (default 80%) instead of waiting
        until 100% to prevent emergency situations.
        
        Args:
            current_tokens: Current token count.
            max_tokens: Maximum context window.
            threshold: Threshold percentage (0.0 - 1.0).
        
        Returns:
            True if compaction should trigger.
        """
        if max_tokens <= 0:
            return False
        
        return (current_tokens / max_tokens) > threshold
    
    def get_status_line(self, current_tokens: int, max_tokens: int) -> str:
        """
        Generate status line with context percentage.
        
        Format: context=65% (5200/8000)
        
        Args:
            current_tokens: Current token count.
            max_tokens: Maximum context window.
        
        Returns:
            Status line string.
        """
        percentage = (current_tokens / max_tokens * 100) if max_tokens > 0 else 0
        return f"context={percentage:.0f}% ({current_tokens}/{max_tokens})"


# Global instance for convenience
_token_counter: TokenCounter | None = None


def get_token_counter() -> TokenCounter:
    """Get or create the global token counter instance."""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter


def count_tokens(text: str) -> int:
    """Convenience function to count tokens in text."""
    return get_token_counter().count_tokens(text)


def count_messages(messages: list[dict[str, Any]]) -> int:
    """Convenience function to count tokens in messages."""
    return get_token_counter().count_messages(messages)
