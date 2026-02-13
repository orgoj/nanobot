"""Secret detection and sanitization utilities."""

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass
class SecretMatch:
    """Represents a detected secret in text."""
    secret_type: str
    start: int
    end: int
    original: str
    masked: str


class SecretSanitizer:
    """
    Detects and masks secrets in text to prevent exposure.
    
    This class identifies common secret patterns (API keys, passwords, tokens)
    and replaces them with masked versions before logging or sending to LLMs.
    """
    
    # Secret patterns with descriptive names
    PATTERNS: dict[str, Pattern] = {
        # API Keys
        'openrouter': re.compile(r'sk-or-[a-zA-Z0-9]{48,64}'),
        'anthropic': re.compile(r'sk-ant-[a-zA-Z0-9]{48,64}'),
        'openai': re.compile(r'sk-[a-zA-Z0-9]{48,64}'),
        'groq': re.compile(r'gsk_[a-zA-Z0-9]{52,64}'),
        'deepseek': re.compile(r'dsk-[a-zA-Z0-9]{32,64}'),
        
        # Generic high-entropy strings that look like API keys
        'generic_api_key': re.compile(r'(?:api[_-]?key|apikey|key)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_-]{32,64})["\']?', re.IGNORECASE),
        
        # Bearer tokens
        'bearer_token': re.compile(r'bearer\s+[a-zA-Z0-9_\-\.]{20,}', re.IGNORECASE),
        
        # Password patterns
        'password_assignment': re.compile(r'(?:password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^"\'\s]{8,})["\']?', re.IGNORECASE),
        
        # Private keys (SSH, etc.)
        'private_key': re.compile(r'-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----', re.IGNORECASE),
        
        # JWT tokens
        'jwt_token': re.compile(r'eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'),
        
        # GitHub tokens
        'github_token': re.compile(r'gh[pousr]_[a-zA-Z0-9]{36,}'),
        
        # Discord tokens
        'discord_token': re.compile(r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}'),
        
        # Database connection strings with passwords
        'db_connection': re.compile(r'(mongodb|postgres|mysql)://[^:]+:([^@]+)@', re.IGNORECASE),
    }
    
    # Words that indicate a secret might follow
    SECRET_INDICATORS = [
        'api_key', 'apikey', 'api-key',
        'password', 'passwd', 'pwd',
        'secret', 'token', 'credential',
        'private_key', 'private-key', 'privatekey',
        'auth', 'authorization',
        'access_key', 'access-key', 'accesskey',
    ]
    
    def __init__(self, mask_char: str = '*', visible_chars: int = 4):
        """
        Initialize the sanitizer.
        
        Args:
            mask_char: Character to use for masking (default: '*')
            visible_chars: Number of characters to show at start/end (default: 4)
        """
        self.mask_char = mask_char
        self.visible_chars = visible_chars
    
    def detect_secrets(self, text: str) -> list[SecretMatch]:
        """
        Detect all secrets in the given text.
        
        Args:
            text: The text to scan for secrets
            
        Returns:
            List of SecretMatch objects representing detected secrets
        """
        matches = []
        
        for secret_type, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                # For patterns with groups, use the first group
                if match.groups():
                    secret_value = match.group(1)
                    start = match.start(1)
                    end = match.end(1)
                else:
                    secret_value = match.group(0)
                    start = match.start()
                    end = match.end()
                
                masked = self._mask_secret(secret_value)
                
                matches.append(SecretMatch(
                    secret_type=secret_type,
                    start=start,
                    end=end,
                    original=secret_value,
                    masked=masked
                ))
        
        # Sort by position and remove overlaps (keep longer matches)
        matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
        filtered = []
        last_end = -1
        for match in matches:
            if match.start >= last_end:
                filtered.append(match)
                last_end = match.end
        
        return filtered
    
    def _mask_secret(self, secret: str) -> str:
        """Mask a secret, showing only first/last few characters."""
        if len(secret) <= self.visible_chars * 2:
            return self.mask_char * len(secret)
        
        prefix = secret[:self.visible_chars]
        suffix = secret[-self.visible_chars:]
        middle_length = len(secret) - (self.visible_chars * 2)
        
        return f"{prefix}{self.mask_char * middle_length}{suffix}"
    
    def sanitize(self, text: str, placeholder: str = '[REDACTED]') -> str:
        """
        Sanitize text by replacing secrets with masked versions.
        
        Args:
            text: The text to sanitize
            placeholder: Text to use if masking fails (default: '[REDACTED]')
            
        Returns:
            Sanitized text with secrets masked
        """
        if not text:
            return text
        
        secrets = self.detect_secrets(text)
        if not secrets:
            return text
        
        # Replace secrets from end to start to preserve positions
        result = text
        for match in reversed(secrets):
            result = result[:match.start] + match.masked + result[match.end:]
        
        return result
    
    def has_secrets(self, text: str) -> bool:
        """Check if text contains any secrets."""
        return len(self.detect_secrets(text)) > 0
    
    def get_secret_types(self, text: str) -> list[str]:
        """Get list of secret types detected in text."""
        secrets = self.detect_secrets(text)
        return list(set(s.secret_type for s in secrets))
    
    def mask_logs(self, text: str, context: str = "") -> str:
        """
        Sanitize text specifically for logging, with extra safety.
        
        Args:
            text: The text to sanitize
            context: Optional context about where this is being logged
            
        Returns:
            Sanitized text safe for logs
        """
        if not text:
            return text
        
        # First pass: standard sanitization
        sanitized = self.sanitize(text)
        
        # Second pass: aggressive masking for potential secrets we missed
        # Look for high-entropy strings that might be secrets
        high_entropy_pattern = re.compile(r'\b[a-zA-Z0-9_-]{32,128}\b')
        
        def mask_high_entropy(match):
            word = match.group(0)
            # Skip common non-secret words
            if word.lower() in {'abcdefghijklmnopqrstuvwxyz', '0123456789'}:
                return word
            # Skip words that look like hashes (already handled)
            if re.match(r'^[a-f0-9]{32,64}$', word, re.IGNORECASE):
                return f"[HASH:{word[:8]}...]"
            # Mask potential missed secrets
            return self._mask_secret(word)
        
        sanitized = high_entropy_pattern.sub(mask_high_entropy, sanitized)
        
        return sanitized


# Global sanitizer instance for convenience
_default_sanitizer = SecretSanitizer()


def sanitize(text: str, placeholder: str = '[REDACTED]') -> str:
    """Convenience function using default sanitizer."""
    return _default_sanitizer.sanitize(text, placeholder)


def has_secrets(text: str) -> bool:
    """Convenience function using default sanitizer."""
    return _default_sanitizer.has_secrets(text)


def mask_logs(text: str, context: str = "") -> str:
    """Convenience function for log masking."""
    return _default_sanitizer.mask_logs(text, context)
