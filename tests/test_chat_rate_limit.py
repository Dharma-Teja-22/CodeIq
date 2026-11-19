import pytest
from unittest.mock import AsyncMock, patch
from neo.core.llm import stream_chat_turn, AssistantMessage, _create_chat_completion_with_retry

@pytest.mark.anyio
async def test_stream_chat_turn_handles_rate_limit():
    with patch("neo.core.llm._create_chat_completion_with_retry", AsyncMock(side_effect=Exception("429 Resource exhausted"))):
        response, usage = await stream_chat_turn(
            messages=[{"role": "user", "content": "Hello Neo"}]
        )
        assert isinstance(response, AssistantMessage)
        assert "Error communicating with AI service" in response.content
