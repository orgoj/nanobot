from unittest.mock import MagicMock

import pytest

from nanobot.providers.litellm_provider import VALID_FINISH_REASONS, LiteLLMProvider


@pytest.mark.asyncio
async def test_finish_reason_normalization():
    """Test that non-standard finish reasons are normalized to 'stop'."""
    provider = LiteLLMProvider(api_key="test-key")

    # Mock response with 'abort' finish reason and some content
    mock_choice = MagicMock()
    mock_choice.finish_reason = "abort"
    mock_choice.message.content = "Some content"
    mock_choice.message.tool_calls = []

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model = "test-model"

    # Test normalization of 'abort' to 'stop' when content is present
    result = provider._parse_response(mock_response)
    assert result.finish_reason == "stop"
    assert result.content == "Some content"

    # Test normalization of other unknown reasons
    mock_choice.finish_reason = "unknown_reason_from_provider"
    result = provider._parse_response(mock_response)
    assert result.finish_reason == "stop"

    # Test that standard reasons are preserved
    for reason in VALID_FINISH_REASONS:
        mock_choice.finish_reason = reason
        result = provider._parse_response(mock_response)
        assert result.finish_reason == reason


@pytest.mark.asyncio
async def test_abort_with_no_content_returns_error():
    """Test that 'abort' with no content returns an error finish reason."""
    provider = LiteLLMProvider(api_key="test-key")

    mock_choice = MagicMock()
    mock_choice.finish_reason = "abort"
    mock_choice.message.content = ""
    mock_choice.message.tool_calls = []

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_response.model = "test-model"

    result = provider._parse_response(mock_response)
    assert result.finish_reason == "error"
    assert "aborted" in result.content
