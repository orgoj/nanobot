"""LiteLLM provider implementation for multi-provider support."""

import json
import os
from typing import Any

import litellm
import litellm.litellm_core_utils.llm_response_utils.convert_dict_to_response as convert_dict_to_response
import litellm.main
from litellm import acompletion
from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.registry import find_by_model, find_gateway

# List of standard finish reasons to protect against non-standard provider outputs
# Rewriting non-standard reasons (like 'abort') to 'stop' ensures internal consistency.
VALID_FINISH_REASONS = [
    "stop",
    "content_filter",
    "function_call",
    "tool_calls",
    "length",
    "guardrail_intervened",
    "eos",
    "finish_reason_unspecified",
    "malformed_function_call",
]


# Global patch across all known LiteLLM entry points for this function
_original_convert = convert_dict_to_response.convert_to_model_response_object
if _original_convert.__name__ != "_patched_convert":

    def _patched_convert(response_object, *args, **kwargs):
        """Monkeypatch to sanitize finish_reason before LiteLLM's Pydantic validation."""
        if isinstance(response_object, dict) and "choices" in response_object:
            for choice in response_object["choices"]:
                raw_reason = choice.get("finish_reason")
                if raw_reason and raw_reason not in VALID_FINISH_REASONS:
                    if raw_reason == "abort":
                        logger.debug("LiteLLM: Sanitizing 'abort' finish_reason to 'stop'")
                    choice["finish_reason"] = "stop"
        return _original_convert(response_object, *args, **kwargs)

    convert_dict_to_response.convert_to_model_response_object = _patched_convert
    litellm.main.convert_to_model_response_object = _patched_convert
    if hasattr(litellm, "convert_to_model_response_object"):
        litellm.convert_to_model_response_object = _patched_convert


class LiteLLMProvider(LLMProvider):
    """
    LLM provider using LiteLLM for multi-provider support.

    Supports OpenRouter, Anthropic, OpenAI, Gemini, MiniMax, and many other providers through
    a unified interface.  Provider-specific logic is driven by the registry
    (see providers/registry.py) — no if-elif chains needed here.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

        # Detect gateway / local deployment.
        # provider_name (from config key) is the primary signal;
        # api_key / api_base are fallback for auto-detection.
        self._gateway = find_gateway(provider_name, api_key, api_base)

        # Configure environment variables
        if api_key:
            self._setup_env(api_key, api_base, default_model)

        if api_base:
            litellm.api_base = api_base

        # Disable LiteLLM logging noise
        litellm.suppress_debug_info = True
        # Drop unsupported parameters for providers (e.g., gpt-5 rejects some params)
        litellm.drop_params = True
        # Don't let litellm crash on unknown finish_reason or other validation errors
        # This is a safety net for providers that return non-standard values (like 'abort')
        litellm.validate = False

    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """Set environment variables based on detected provider."""
        spec = self._gateway or find_by_model(model)
        if not spec:
            return

        # Gateway/local overrides existing env; standard provider doesn't
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

        # Resolve env_extras placeholders:
        #   {api_key}  → user's API key
        #   {api_base} → user's api_base, falling back to spec.default_api_base
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base)
            os.environ.setdefault(env_name, resolved)

    def _resolve_model(self, model: str) -> str:
        """Resolve model name by applying provider/gateway prefixes."""
        if self._gateway:
            # Gateway mode: apply gateway prefix, skip provider-specific prefixes
            prefix = self._gateway.litellm_prefix
            if self._gateway.strip_model_prefix:
                model = model.split("/")[-1]
            if prefix and not model.startswith(f"{prefix}/"):
                model = f"{prefix}/{model}"
            return model

        # Standard mode: auto-prefix for known providers
        spec = find_by_model(model)
        if spec and spec.litellm_prefix:
            if not any(model.startswith(s) for s in spec.skip_prefixes):
                model = f"{spec.litellm_prefix}/{model}"

        return model

    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """Apply model-specific parameter overrides from the registry."""
        model_lower = model.lower()
        spec = find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: float | None = None,
    ) -> LLMResponse:
        """
        Send a chat completion request via LiteLLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            timeout: Optional timeout in seconds.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        model = self._resolve_model(model or self.default_model)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if timeout:
            kwargs["timeout"] = timeout

        # Apply model-specific overrides (e.g. kimi-k2.5 temperature)
        self._apply_model_overrides(model, kwargs)

        # Pass api_key directly — more reliable than env vars alone
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Pass api_base for custom endpoints
        if self.api_base:
            kwargs["api_base"] = self.api_base

        # Pass extra headers (e.g. APP-Code for AiHubMix)
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            # Return error as content for graceful handling
            logger.error(f"LLM call failed ({model}): {str(e)}")
            # If it's a validation error, let's try to see what exactly failed
            if "ValidationError" in str(e):
                logger.debug(f"Validation error details: {e}")

            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into our standard format."""
        if not response or not hasattr(response, "choices") or not response.choices:
            logger.warning(f"Empty or invalid response object: {response}")
            return LLMResponse(
                content="Error: Empty or invalid response from LLM provider.",
                finish_reason="error",
            )

        choice = response.choices[0]
        message = choice.message

        # Handle 'abort' and other non-standard finish reasons
        # Use getattr because Pydantic might have failed to populate it if it was an unknown literal
        finish_reason = getattr(choice, "finish_reason", None) or "stop"

        if finish_reason not in VALID_FINISH_REASONS:
            if finish_reason == "abort":
                logger.error(
                    f"LLM call was aborted (finish_reason='abort'). Model: {getattr(response, 'model', 'unknown')}. "
                    f"Usage: {getattr(response, 'usage', 'unknown')}"
                )
                # If aborted and no content, mark as error
                if not message.content and not (
                    hasattr(message, "tool_calls") and message.tool_calls
                ):
                    return LLMResponse(
                        content="Error: LLM call was aborted by provider (likely timeout or overload).",
                        finish_reason="error",
                    )

            # Rewrite unknown/non-standard reasons to "stop" (internal response sanitization)
            finish_reason = "stop"

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                # Parse arguments from JSON string if needed
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}

                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        usage = {}
        if hasattr(response, "usage") and response.usage:
            # LiteLLM usage might be a dict or an object
            u = response.usage
            usage = {
                "prompt_tokens": getattr(u, "prompt_tokens", 0),
                "completion_tokens": getattr(u, "completion_tokens", 0),
                "total_tokens": getattr(u, "total_tokens", 0),
            }

        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        """Get the default model."""
        return self.default_model
