"""Update configuration tool for nanobot.

This tool provides a centralized way to update configuration values
from CLI, chat, or API calls. It handles validation, type conversion,
and security considerations.
"""

from pathlib import Path
from typing import Any, get_origin, get_args
from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.config.loader import load_config, save_config, get_config_path
from nanobot.config.schema import Config, ToolsConfig, RoutingConfig
from nanobot.security.sanitizer import SecretSanitizer


class ConfigUpdateError(Exception):
    """Error during configuration update."""
    pass


class UpdateConfigTool(Tool):
    """
    Tool to update nanobot configuration values.
    
    This tool provides secure configuration updates with:
    - Path validation (dot notation like 'providers.openrouter.apiKey')
    - Type validation and conversion
    - Secret detection and masking in logs
    - Backup before changes
    - Support for arrays (append/remove)
    """
    
    name = "update_config"
    
    # Configuration schema for validation
    SCHEMA = {
        'agents': {
            'description': 'Agent behavior settings',
            'required_for_startup': False,
            'fields': {
                'defaults.workspace': {'type': 'path', 'default': '~/.nanobot/workspace'},
                'defaults.model': {'type': 'string', 'required': True},
                'defaults.max_tokens': {'type': 'integer', 'default': 8192, 'min': 1, 'max': 128000},
                'defaults.temperature': {'type': 'float', 'default': 0.7, 'min': 0.0, 'max': 2.0},
                'defaults.max_tool_iterations': {'type': 'integer', 'default': 20, 'min': 1, 'max': 100},
            }
        },
        'providers': {
            'description': 'LLM API providers',
            'required_for_startup': True,
            'required_hint': 'At least one provider with apiKey is required',
            'providers': {
                'openrouter': {
                    'fields': {
                        'apiKey': {'type': 'string', 'pattern': r'^sk-or-v1-', 'help': 'Get from https://openrouter.ai/keys'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'anthropic/claude-opus-4-5',
                        'openai/gpt-4o',
                        'deepseek/deepseek-chat-v3-0324',
                    ]
                },
                'anthropic': {
                    'fields': {
                        'apiKey': {'type': 'string', 'pattern': r'^sk-ant-', 'help': 'Get from https://console.anthropic.com/'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'claude-3-5-sonnet-20241022',
                        'claude-3-opus-20240229',
                    ]
                },
                'openai': {
                    'fields': {
                        'apiKey': {'type': 'string', 'pattern': r'^sk-', 'help': 'Get from https://platform.openai.com/api-keys'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'gpt-4o',
                        'gpt-4o-mini',
                        'gpt-4-turbo',
                    ]
                },
                'groq': {
                    'fields': {
                        'apiKey': {'type': 'string', 'pattern': r'^gsk_', 'help': 'Get from https://console.groq.com/keys'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'llama-3.3-70b-versatile',
                        'mixtral-8x7b-32768',
                    ]
                },
                'deepseek': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://platform.deepseek.com/api_keys'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'deepseek-chat-v3-0324',
                        'deepseek-coder-v2',
                    ]
                },
                'moonshot': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://platform.moonshot.cn/'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'moonshotai/kimi-k2.5',
                    ]
                },
                'gemini': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://aistudio.google.com/app/apikey'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'gemini-1.5-pro',
                        'gemini-1.5-flash',
                    ]
                },
                'aihubmix': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://aihubmix.com/'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'gpt-4o',
                        'claude-3-5-sonnet',
                        'deepseek-chat',
                    ]
                },
                'dashscope': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://dashscope.console.aliyun.com/'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'qwen-turbo',
                        'qwen-plus',
                        'qwen-max',
                    ]
                },
                'zhipu': {
                    'fields': {
                        'apiKey': {'type': 'string', 'help': 'Get from https://open.bigmodel.cn/'},
                        'apiBase': {'type': 'url', 'default': None},
                    },
                    'models': [
                        'glm-4',
                        'glm-4-plus',
                        'glm-4-long',
                    ]
                },
                'vllm': {
                    'fields': {
                        'apiKey': {'type': 'string', 'default': 'dummy', 'help': 'Any non-empty string for local servers'},
                        'apiBase': {'type': 'url', 'default': 'http://localhost:8000/v1', 'help': 'Your vLLM server URL'},
                    },
                    'models': [
                        'local-model',
                    ],
                    'setup_note': 'Requires running vLLM server. See README for setup instructions.',
                },
            }
        },
        'channels': {
            'description': 'Chat channel integrations',
            'required_for_startup': False,
            'channels': {
                'telegram': {
                    'difficulty': 'Easy',
                    'fields': {
                        'enabled': {'type': 'boolean', 'default': False},
                        'token': {'type': 'string', 'help': 'Bot token from @BotFather (format: 123456:ABC-DEF...). Steps: 1) Message @BotFather 2) Type /newbot 3) Copy the token'},
                        'allowFrom': {'type': 'array', 'item_type': 'string', 'help': 'Allowed user IDs or usernames (comma-separated, e.g.: user1, user2, 123456789)'},
                    },
                },
                'discord': {
                    'difficulty': 'Easy',
                    'fields': {
                        'enabled': {'type': 'boolean', 'default': False},
                        'token': {'type': 'string', 'help': 'Get from Discord Developer Portal'},
                        'allowFrom': {'type': 'array', 'item_type': 'string', 'help': 'Allowed Discord user IDs (comma-separated)'},
                    },
                },
                'whatsapp': {
                    'difficulty': 'Medium',
                    'setup_note': 'Requires Node.js bridge. Run: nanobot channels login',
                    'fields': {
                        'enabled': {'type': 'boolean', 'default': False},
                        'bridgeUrl': {'type': 'url', 'default': 'ws://localhost:3001'},
                        'allowFrom': {'type': 'array', 'item_type': 'string', 'help': 'Allowed phone numbers (comma-separated, e.g.: +1234567890, +0987654321)'},
                    },
                },
                'slack': {
                    'difficulty': 'Medium',
                    'fields': {
                        'enabled': {'type': 'boolean', 'default': False},
                        'mode': {'type': 'enum', 'options': ['socket', 'webhook'], 'default': 'socket'},
                        'botToken': {'type': 'string', 'help': 'Bot token (starts with xoxb-)'},
                        'appToken': {'type': 'string', 'help': 'App token (starts with xapp-)'},
                    },
                },
                'email': {
                    'difficulty': 'Medium',
                    'fields': {
                        'enabled': {'type': 'boolean', 'default': False},
                        'consentGranted': {'type': 'boolean', 'default': False, 'help': 'Explicit permission to access mailbox'},
                        'imapHost': {'type': 'string'},
                        'imapUsername': {'type': 'string'},
                        'imapPassword': {'type': 'string'},
                        'smtpHost': {'type': 'string'},
                        'smtpUsername': {'type': 'string'},
                        'smtpPassword': {'type': 'string'},
                        'fromAddress': {'type': 'string'},
                        'allowFrom': {'type': 'array', 'item_type': 'string', 'help': 'Allowed sender email addresses (comma-separated, e.g.: user@example.com, admin@domain.com)'},
                    },
                },
            }
        },
        'tools': {
            'description': 'Tool behavior settings',
            'required_for_startup': False,
            'fields': {
                'restrictToWorkspace': {'type': 'boolean', 'default': False, 'help': 'Sandbox: restrict file access to workspace only'},
                'evolutionary': {'type': 'boolean', 'default': False, 'help': 'Allow bot to self-improve (see docs)'},
                'allowedPaths': {'type': 'array', 'item_type': 'path', 'help': 'Paths bot can access when evolutionary=true'},
                'protectedPaths': {'type': 'array', 'item_type': 'path', 'default': ['~/.nanobot/config.json']},
                'exec.timeout': {'type': 'integer', 'default': 60, 'min': 1, 'max': 3600},
                'web.search.apiKey': {'type': 'string', 'help': 'Brave Search API key (optional)'},
                'web.search.maxResults': {'type': 'integer', 'default': 5, 'min': 1, 'max': 20},
            }
        },
        'gateway': {
            'description': 'Gateway server settings',
            'required_for_startup': False,
            'fields': {
                'host': {'type': 'string', 'default': '0.0.0.0'},
                'port': {'type': 'integer', 'default': 18790, 'min': 1, 'max': 65535},
            }
        },
        'routing': {
            'description': 'Smart routing automatically selects the best model based on query complexity',
            'required_for_startup': False,
            'fields': {
                'enabled': {'type': 'boolean', 'default': True, 'help': 'Enable smart routing (recommended)'},
            },
            'tiers': {
                'description': 'Model tiers for different query complexities',
                'simple': {
                    'description': 'Quick queries, greetings, simple facts',
                    'fields': {
                        'model': {'type': 'string', 'default': 'deepseek/deepseek-chat-v3-0324'},
                        'costPerMtok': {'type': 'float', 'default': 0.27},
                        'secondaryModel': {'type': 'string', 'default': 'deepseek/deepseek-chat-v3.1'},
                    }
                },
                'medium': {
                    'description': 'General questions, explanations',
                    'fields': {
                        'model': {'type': 'string', 'default': 'openai/gpt-4.1-mini'},
                        'costPerMtok': {'type': 'float', 'default': 0.40},
                        'secondaryModel': {'type': 'string', 'default': 'openai/gpt-4o-mini'},
                    }
                },
                'complex': {
                    'description': 'Deep analysis, debugging',
                    'fields': {
                        'model': {'type': 'string', 'default': 'anthropic/claude-sonnet-4.5'},
                        'costPerMtok': {'type': 'float', 'default': 3.0},
                        'secondaryModel': {'type': 'string', 'default': 'anthropic/claude-sonnet-4'},
                    }
                },
                'reasoning': {
                    'description': 'Multi-step logic, proofs, planning',
                    'fields': {
                        'model': {'type': 'string', 'default': 'openai/o3'},
                        'costPerMtok': {'type': 'float', 'default': 2.0},
                        'secondaryModel': {'type': 'string', 'default': 'openai/gpt-4o'},
                    }
                },
                'coding': {
                    'description': 'Code generation, refactoring, debugging',
                    'fields': {
                        'model': {'type': 'string', 'default': 'moonshotai/kimi-k2.5'},
                        'costPerMtok': {'type': 'float', 'default': 0.45},
                        'secondaryModel': {'type': 'string', 'default': 'anthropic/claude-sonnet-4'},
                    }
                },
            },
            'advanced': {
                'description': 'Advanced routing settings',
                'clientClassifier.minConfidence': {'type': 'float', 'default': 0.85, 'min': 0.0, 'max': 1.0, 'help': 'Confidence threshold for client-side classification'},
                'llmClassifier.model': {'type': 'string', 'default': 'gpt-4o-mini', 'help': 'Model for LLM-assisted classification'},
                'sticky.contextWindow': {'type': 'integer', 'default': 5, 'min': 1, 'max': 20, 'help': 'Context window for sticky routing'},
                'sticky.downgradeConfidence': {'type': 'float', 'default': 0.9, 'min': 0.0, 'max': 1.0, 'help': 'Confidence threshold for tier downgrade'},
                'autoCalibration.enabled': {'type': 'boolean', 'default': True, 'help': 'Enable automatic routing calibration'},
            }
        },
    }
    
    def __init__(self):
        self.sanitizer = SecretSanitizer()
    
    @property
    def description(self) -> str:
        return """Update nanobot configuration values.
        
Use this tool to change configuration settings. Paths use dot notation:
- providers.openrouter.apiKey
- channels.telegram.enabled
- agents.defaults.model

Examples:
- Update OpenRouter key: {"path": "providers.openrouter.apiKey", "value": "sk-or-..."}
- Enable Telegram: {"path": "channels.telegram.enabled", "value": true}
- Change model: {"path": "agents.defaults.model", "value": "anthropic/claude-opus-4-5"}
"""
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Configuration path using dot notation (e.g., 'providers.openrouter.apiKey')"
                },
                "value": {
                    "type": "object",
                    "description": "New value to set (string, boolean, number, or array)"
                },
                "operation": {
                    "type": "string",
                    "enum": ["set", "append", "remove"],
                    "description": "Operation to perform: 'set' (default), 'append' to array, or 'remove' from array"
                }
            },
            "required": ["path", "value"]
        }
    
    async def execute(self, path: str, value: Any, operation: str = "set", **kwargs) -> str:
        """
        Update a configuration value.
        
        Args:
            path: Dot-notation path (e.g., 'providers.openrouter.apiKey')
            value: New value
            operation: 'set', 'append', or 'remove'
            
        Returns:
            Success message or error
        """
        try:
            # Load current config
            config = load_config()
            
            # Parse the path
            parts = path.split('.')
            if len(parts) < 2:
                return f"Error: Invalid path '{path}'. Must have at least 2 parts (e.g., 'providers.openrouter.apiKey')"
            
            # Get schema info for this path
            schema_info = self._get_schema_info(parts)
            
            # Validate and convert value
            validated_value = self._validate_value(value, schema_info, path)
            if validated_value is None:
                return f"Error: Invalid value '{value}' for path '{path}'"
            
            # Check for secrets in the value
            if isinstance(validated_value, str) and self.sanitizer.has_secrets(validated_value):
                # Secrets detected - log at debug level only
                logger.debug("Configuration update contains secrets (stored securely)")
            
            # Backup existing config
            self._backup_config()
            
            # Navigate to the target and update
            success = self._update_config_value(config, parts, validated_value, operation)
            
            if not success:
                return f"Error: Could not update path '{path}'"
            
            # Save the config
            save_config(config)
            
            # Log success at debug level only (avoid cluttering CLI output)
            logger.debug(f"Configuration updated: {path}")
            
            return f"✓ Updated {path} successfully"
            
        except ConfigUpdateError as e:
            logger.error(f"Config update failed: {e}")
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error updating config: {e}")
            return f"Error: Failed to update configuration - {str(e)}"
    
    def _get_schema_info(self, parts: list[str]) -> dict:
        """Get schema information for a configuration path."""
        category = parts[0]
        
        if category not in self.SCHEMA:
            return {}
        
        schema = self.SCHEMA[category]
        
        # Navigate nested schema
        current = schema
        for part in parts[1:]:
            if 'fields' in current and part in current['fields']:
                current = current['fields'][part]
            elif 'providers' in current and part in current['providers']:
                current = current['providers'][part]
            elif 'channels' in current and part in current['channels']:
                current = current['channels'][part]
            else:
                break
        
        return current if isinstance(current, dict) else {}
    
    def _validate_value(self, value: Any, schema: dict, path: str) -> Any:
        """Validate and convert a value according to schema."""
        field_type = schema.get('type', 'string')
        
        try:
            if field_type == 'string':
                str_value = str(value)
                # Check pattern if specified
                if 'pattern' in schema:
                    import re
                    if not re.match(schema['pattern'], str_value):
                        raise ConfigUpdateError(
                            f"Value does not match required pattern. {schema.get('help', '')}"
                        )
                return str_value
            
            elif field_type == 'boolean':
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', 'yes', '1', 'on')
                return bool(value)
            
            elif field_type == 'integer':
                int_value = int(value)
                if 'min' in schema and int_value < schema['min']:
                    raise ConfigUpdateError(f"Value must be >= {schema['min']}")
                if 'max' in schema and int_value > schema['max']:
                    raise ConfigUpdateError(f"Value must be <= {schema['max']}")
                return int_value
            
            elif field_type == 'float':
                float_value = float(value)
                if 'min' in schema and float_value < schema['min']:
                    raise ConfigUpdateError(f"Value must be >= {schema['min']}")
                if 'max' in schema and float_value > schema['max']:
                    raise ConfigUpdateError(f"Value must be <= {schema['max']}")
                return float_value
            
            elif field_type == 'array':
                if isinstance(value, list):
                    # Ensure all items are strings
                    item_type = schema.get('item_type', 'string')
                    if item_type == 'string':
                        return [str(item) for item in value]
                    return value
                if isinstance(value, str):
                    # Parse comma-separated or JSON array
                    try:
                        import json
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            item_type = schema.get('item_type', 'string')
                            if item_type == 'string':
                                return [str(item) for item in parsed]
                            return parsed
                        # Single value parsed as non-list
                        return [str(parsed)]
                    except:
                        return [item.strip() for item in value.split(',') if item.strip()]
                # Single non-string value (e.g., int)
                return [str(value)]
            
            elif field_type == 'enum':
                options = schema.get('options', [])
                str_value = str(value)
                if str_value not in options:
                    raise ConfigUpdateError(f"Value must be one of: {', '.join(options)}")
                return str_value
            
            elif field_type == 'path':
                # Expand user home directory
                path_value = str(value)
                if path_value.startswith('~'):
                    path_value = str(Path.home() / path_value[2:])
                return path_value
            
            elif field_type == 'url':
                url_value = str(value)
                if url_value and not url_value.startswith(('http://', 'https://', 'ws://', 'wss://')):
                    raise ConfigUpdateError("Value must be a valid URL")
                return url_value if url_value else None
            
            else:
                return str(value)
                
        except (ValueError, TypeError) as e:
            raise ConfigUpdateError(f"Invalid value type. Expected {field_type}, got {type(value).__name__}")
    
    def _backup_config(self):
        """Create a backup of the current config file."""
        config_path = get_config_path()
        if config_path.exists():
            backup_path = config_path.with_suffix('.json.backup')
            try:
                import shutil
                shutil.copy2(config_path, backup_path)
                logger.debug(f"Config backed up to {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to backup config: {e}")
    
    def _update_config_value(self, config: Config, parts: list[str], value: Any, operation: str) -> bool:
        """
        Update a value in the config object.
        
        Args:
            config: Config object to update
            parts: Path parts (can be camelCase or snake_case)
            value: New value
            operation: 'set', 'append', or 'remove'
            
        Returns:
            True if successful
        """
        from nanobot.config.loader import camel_to_snake
        
        # Convert parts to snake_case for Python attribute access
        # Pydantic models use snake_case for attribute names (e.g., api_key, not apiKey)
        snake_parts = [camel_to_snake(p) for p in parts]
        
        try:
            # Navigate to the parent object
            current = config
            for part in snake_parts[:-1]:
                if hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return False
            
            # Get the final attribute name
            final_part = snake_parts[-1]
            
            if operation == 'set':
                if hasattr(current, final_part):
                    setattr(current, final_part, value)
                    return True
                return False
            
            elif operation == 'append':
                # Append to array
                if hasattr(current, final_part):
                    arr = getattr(current, final_part)
                    if isinstance(arr, list):
                        if value not in arr:
                            arr.append(value)
                        return True
                return False
            
            elif operation == 'remove':
                # Remove from array
                if hasattr(current, final_part):
                    arr = getattr(current, final_part)
                    if isinstance(arr, list) and value in arr:
                        arr.remove(value)
                        return True
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error updating config value: {e}")
            return False
    
    def get_required_for_startup(self) -> dict:
        """Get configuration required for startup."""
        required = {}
        
        # Check providers - at least one with apiKey
        required['providers'] = {
            'description': 'At least one LLM provider with API key',
            'providers': list(self.SCHEMA['providers']['providers'].keys()),
        }
        
        return required
    
    def validate_model_for_routing(self, model: str) -> dict:
        """
        Validate if a model is compatible with configured providers.
        
        Args:
            model: Model string (e.g., "anthropic/claude-3-opus" or "gpt-4o")
            
        Returns:
            Dict with validation results:
            - valid: bool - Whether model format is valid
            - provider: str - Detected provider name
            - provider_configured: bool - Whether provider has API key
            - warning: str - Warning message if provider not configured
            - suggestion: str - Suggested alternative if available
        """
        config = load_config()
        result = {
            'valid': True,
            'provider': None,
            'provider_configured': False,
            'warning': None,
            'suggestion': None
        }
        
        if not model or not isinstance(model, str):
            result['valid'] = False
            result['warning'] = "Model name cannot be empty"
            return result
        
        # Parse provider from model string
        # Format can be: "provider/model" or just "model"
        provider_name = None
        
        if '/' in model:
            # Extract provider from "provider/model" format
            provider_name = model.split('/')[0].lower()
            
            # Map common aliases
            provider_aliases = {
                'anthropic': 'anthropic',
                'claude': 'anthropic',
                'openai': 'openai',
                'gpt': 'openai',
                'deepseek': 'deepseek',
                'groq': 'groq',
                'moonshotai': 'moonshot',
                'moonshot': 'moonshot',
                'kimi': 'moonshot',
                'gemini': 'gemini',
                'zhipu': 'zhipu',
                'dashscope': 'dashscope',
                'qwen': 'dashscope',
                'aihubmix': 'aihubmix',
                'openrouter': 'openrouter',
                'vllm': 'vllm',
            }
            provider_name = provider_aliases.get(provider_name, provider_name)
        else:
            # Try to detect provider from model name patterns
            model_lower = model.lower()
            if 'claude' in model_lower:
                provider_name = 'anthropic'
            elif 'gpt' in model_lower or model_lower.startswith('o1') or model_lower.startswith('o3'):
                provider_name = 'openai'
            elif 'deepseek' in model_lower:
                provider_name = 'deepseek'
            elif 'llama' in model_lower or 'mixtral' in model_lower:
                provider_name = 'groq'
            elif 'kimi' in model_lower:
                provider_name = 'moonshot'
            elif 'gemini' in model_lower:
                provider_name = 'gemini'
        
        result['provider'] = provider_name
        
        if not provider_name:
            # Can't determine provider - assume it's valid but warn
            result['warning'] = f"Could not determine provider for model '{model}'. Ensure you have the correct provider configured."
            return result
        
        # Check if provider is configured
        provider_config = getattr(config.providers, provider_name, None)
        if provider_config and provider_config.api_key:
            result['provider_configured'] = True
        else:
            result['provider_configured'] = False
            
            # Get list of configured providers for suggestion
            configured = [
                name for name in self.SCHEMA['providers']['providers'].keys()
                if getattr(getattr(config.providers, name, None), 'api_key', None)
            ]
            
            # Special handling for gateway providers
            is_gateway = provider_name in ['openrouter', 'aihubmix']
            
            if configured:
                if is_gateway:
                    result['warning'] = (
                        f"Model '{model}' requires {provider_name.title()} gateway, "
                        f"but no API key is configured."
                    )
                    result['suggestion'] = (
                        f"{provider_name.title()} can route to all major AI models. "
                        f"Run 'nanobot configure' to add your {provider_name.title()} API key."
                    )
                else:
                    result['warning'] = (
                        f"Model '{model}' requires {provider_name.title()} provider, "
                        f"but no API key is configured."
                    )
                    result['suggestion'] = (
                        f"Configured providers: {', '.join(configured)}. "
                        f"Run 'nanobot configure' to add {provider_name.title()}."
                    )
            else:
                if is_gateway:
                    result['warning'] = (
                        f"Model '{model}' requires {provider_name.title()} gateway."
                    )
                    result['suggestion'] = (
                        f"{provider_name.title()} provides access to multiple AI models through a single API. "
                        f"Run 'nanobot onboard' to configure your first provider."
                    )
                else:
                    result['warning'] = (
                        f"Model '{model}' requires {provider_name.title()} provider, "
                        f"but no providers are configured yet."
                    )
                    result['suggestion'] = "Run 'nanobot onboard' to configure your first provider."
        
        return result
    
    def get_config_summary(self) -> dict:
        """Get a summary of current configuration."""
        config = load_config()
        
        summary = {
            'providers': {},
            'channels': {},
            'has_required_config': False,
        }
        
        # Check providers
        for provider_name in self.SCHEMA['providers']['providers'].keys():
            provider = getattr(config.providers, provider_name, None)
            if provider and provider.api_key:
                summary['providers'][provider_name] = {
                    'configured': True,
                    'has_key': True,
                }
            else:
                summary['providers'][provider_name] = {
                    'configured': False,
                    'has_key': False,
                }
        
        # Check if any provider is configured
        summary['has_required_config'] = any(
            p['has_key'] for p in summary['providers'].values()
        )
        
        # Check channels
        for channel_name in self.SCHEMA['channels']['channels'].keys():
            channel = getattr(config.channels, channel_name, None)
            if channel:
                summary['channels'][channel_name] = {
                    'enabled': getattr(channel, 'enabled', False),
                }
        
        return summary
