from unittest.mock import MagicMock

import pytest

from nanobot.providers.litellm_provider import VALID_FINISH_REASONS, LiteLLMProvider


@pytest.mark.asyncio
async def test_finish_reason_normalization():
    """Test that non-standard finish reasons are normalized to 'stop' via monkeypatch."""
    # Test the monkeypatch directly
    from nanobot.providers.litellm_provider import _patched_convert

    response_dict = {
        "choices": [
            {"finish_reason": "abort", "message": {"content": "Some content"}},
            {"finish_reason": "unknown_reason", "message": {"content": "Other content"}},
        ]
    }

    # We need to mock the original_convert because it will fail on a dict mock
    # or we can just check if it modifies the dict
    def mock_original(obj, *args, **kwargs):
        return obj

    import nanobot.providers.litellm_provider

    nanobot.providers.litellm_provider._original_convert = mock_original

    _patched_convert(response_dict)

    assert response_dict["choices"][0]["finish_reason"] == "stop"
    assert response_dict["choices"][1]["finish_reason"] == "stop"

    # Test that standard reasons are preserved
    for reason in VALID_FINISH_REASONS:
        response_dict = {"choices": [{"finish_reason": reason}]}
        _patched_convert(response_dict)
        assert response_dict["choices"][0]["finish_reason"] == reason


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
