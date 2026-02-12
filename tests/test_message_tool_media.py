import pytest

from nanobot.agent.tools.message import MessageTool


@pytest.mark.asyncio
async def test_message_tool_passes_media() -> None:
    sent = {}

    async def _send(msg):
        sent["msg"] = msg

    tool = MessageTool(send_callback=_send, default_channel="feishu", default_chat_id="ou_123")
    result = await tool.execute(content="hi", media=["/tmp/a.png"])
    assert "Message sent" in result
    assert sent["msg"].media == ["/tmp/a.png"]
