import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from codeiq_dev.core.llm import _is_rate_limit_or_resource_exhausted, _create_chat_completion_with_retry

def test_rate_limit_exception_predicate():
    assert _is_rate_limit_or_resource_exhausted(Exception("Error code: 429 - Rate limit exceeded")) is True
    assert _is_rate_limit_or_resource_exhausted(Exception("Resource exhausted: Please try again later.")) is True
    assert _is_rate_limit_or_resource_exhausted(Exception("Quota exceeded for current tier.")) is True
    assert _is_rate_limit_or_resource_exhausted(Exception("Error code: 401 - Unauthorized")) is False
    assert _is_rate_limit_or_resource_exhausted(Exception("Error code: 404 - Not Found")) is False


@pytest.mark.anyio
async def test_retry_on_resource_exhausted_success():
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="Success after retries"))]

    mock_client_create = AsyncMock(
        side_effect=[
            Exception("429 Resource exhausted"),
            Exception("Resource exhausted"),
            fake_response
        ]
    )

    with patch("codeiq_dev.core.llm.client.chat.completions.create", mock_client_create):
        result = await _create_chat_completion_with_retry({"model": "test-model", "messages": []})
        assert result.choices[0].message.content == "Success after retries"
        assert mock_client_create.call_count == 3


@pytest.mark.anyio
async def test_retry_exhausted_raises_error():
    mock_client_create = AsyncMock(
        side_effect=Exception("429 Resource exhausted")
    )

    with patch("codeiq_dev.core.llm.client.chat.completions.create", mock_client_create):
        with pytest.raises(Exception, match="429 Resource exhausted"):
            await _create_chat_completion_with_retry({"model": "test-model", "messages": []})
        
        assert mock_client_create.call_count == 5
