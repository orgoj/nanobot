import json
import logging
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

class TokenCounter:
    """
    Helper to estimate token usage.
    Tries to use tiktoken if available, otherwise falls back to char estimation.
    """
    _encoding = None

    @classmethod
    def get_encoding(cls):
        if cls._encoding is None:
            try:
                import tiktoken
                cls._encoding = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                cls._encoding = False
        return cls._encoding

    @classmethod
    def count_text(cls, text: str) -> int:
        enc = cls.get_encoding()
        if enc:
            return len(enc.encode(text))
        else:
            # Fallback for Chinese/Mix: 1 token ~= 1.5 chars is safer than 2.5
            # For pure English, 1 token ~= 4 chars.
            # We'll use a safer heuristic for the mixed local environment.
            return int(len(text) / 1.5)

    @classmethod
    def count_messages(cls, messages: List[Dict[str, Any]]) -> int:
        """
        Estimate tokens for a list of messages.
        """
        enc = cls.get_encoding()
        if enc:
            # Tiktoken chat format estimation (approximate)
            num_tokens = 0
            for message in messages:
                num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
                for key, value in message.items():
                    if isinstance(value, str):
                        num_tokens += len(enc.encode(value))
                    elif isinstance(value, list):
                        # Handle tool calls / content parts
                        num_tokens += len(enc.encode(json.dumps(value)))
                if "name" in message:  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
            num_tokens += 2  # every reply is primed with <im_start>assistant
            return num_tokens
        else:
            # Rough fallback
            return cls.count_text(json.dumps(messages))

class ContextGuard:
    """
    Guards the context window size to prevent LLM errors.
    """
    
    # Default safe limit (can be overridden by model config)
    DEFAULT_LIMIT = 8192 
    
    # Trigger compaction when usage > limit * threshold
    THRESHOLD = 0.85

    # Known model limits (conservative)
    MODEL_LIMITS = {
        # OpenAI
        "gpt-4o": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
        # Anthropic
        "claude-3-opus-20240229": 200000,
        "claude-3-sonnet-20240229": 200000,
        "claude-3-haiku-20240307": 200000,
        "claude-3-5-sonnet-20240620": 200000,
        # Gemini
        "gemini-1.5-pro": 1000000, # Technically 1M or 2M
        "gemini-1.5-flash": 1000000,
        "gemini-pro": 30720,
        # DeepSeek
        "deepseek-chat": 32768,
        "deepseek-coder": 32768,
        # Gemini 2/3
        "gemini-3": 128000,
        "gemini-2": 1000000,
        "gemini": 32768, # Default fallback for older gemini
    }

    def __init__(self, limit: int | None = None, model: str | None = None):
        if limit:
            self.limit = limit
        elif model:
            # Fuzzy match model name
            self.limit = self.DEFAULT_LIMIT
            for key, val in self.MODEL_LIMITS.items():
                if key in model.lower():
                    self.limit = val
                    break
        else:
            self.limit = self.DEFAULT_LIMIT

    def evaluate(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check if messages fit within the limit.
        """
        usage = TokenCounter.count_messages(messages)
        is_safe = usage < self.limit
        should_compact = usage > (self.limit * self.THRESHOLD)
        
        return {
            "usage": usage,
            "limit": self.limit,
            "is_safe": is_safe,
            "should_compact": should_compact,
            "utilization": usage / self.limit
        }

    def prune_old_messages(self, messages: List[Dict[str, Any]], keep_last: int = 10) -> List[Dict[str, Any]]:
        """
        Simple pruning strategy: keep system/bootstrap, summarize middle?
        For now: just return the slice to prompt the summarizer.
        """
        # Identify system messages (usually at start)
        system_msgs = [m for m in messages if m.get("role") == "system"]
        chat_msgs = [m for m in messages if m.get("role") != "system"]
        
        if len(chat_msgs) <= keep_last:
            return messages
            
        # We need to prune `chat_msgs`
        # But we can't just drop them, we need to summarize them.
        # This function just helps identify WHAT to prune.
        return system_msgs + chat_msgs[-keep_last:]
