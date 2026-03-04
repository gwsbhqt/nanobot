"""Test message tool suppress logic for final replies."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.message import MessageTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.feishu import FeishuChannel
from nanobot.config.schema import FeishuConfig
from nanobot.providers.base import LLMResponse, ToolCallRequest


def _make_loop(tmp_path: Path) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model", memory_window=10)


class TestMessageToolSuppressLogic:
    """Final reply suppressed only when message tool sends to the same target."""

    @pytest.mark.asyncio
    async def test_suppress_when_sent_to_same_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Hello", "channel": "feishu", "chat_id": "chat123"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Done", tool_calls=[]),
        ])
        loop.provider.chat = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Send")
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert result is None  # suppressed

    @pytest.mark.asyncio
    async def test_not_suppress_when_sent_to_different_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Forward content", "channel": "feishu", "chat_id": "chat456"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="I've sent the message.", tool_calls=[]),
        ])
        loop.provider.chat = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Send message")
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert sent[0].channel == "feishu"
        assert sent[0].chat_id == "chat456"
        assert result is not None  # not suppressed
        assert result.channel == "feishu"

    @pytest.mark.asyncio
    async def test_not_suppress_when_no_message_tool_used(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.provider.chat = AsyncMock(return_value=LLMResponse(content="Hello!", tool_calls=[]))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Hi")
        result = await loop._process_message(msg)

        assert result is not None
        assert "Hello" in result.content

    @pytest.mark.asyncio
    async def test_retry_once_when_llm_returns_empty_content(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        calls = iter([
            LLMResponse(content="", tool_calls=[]),
            LLMResponse(content="pwd 是 /Users/bytedance/project/nanobot", tool_calls=[]),
        ])
        loop.provider.chat = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="是的")
        result = await loop._process_message(msg)

        assert result is not None
        assert "pwd 是" in result.content
        assert loop.provider.chat.await_count == 2

    @pytest.mark.asyncio
    async def test_fallback_when_empty_content_after_retry(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.provider.chat = AsyncMock(side_effect=[
            LLMResponse(content="", tool_calls=[]),
            LLMResponse(content="", tool_calls=[]),
        ])
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="是的")
        result = await loop._process_message(msg)

        assert result is not None
        assert result.content == "I've completed processing but have no response to give."
        assert loop.provider.chat.await_count == 2

    @pytest.mark.asyncio
    async def test_new_clears_session_when_archival_fails(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._consolidate_memory = AsyncMock(return_value=False)

        session = loop.sessions.get_or_create("feishu:chat123")
        session.messages = [
            {"role": "user", "content": "hi", "timestamp": "2026-03-02T18:00:00"},
            {"role": "assistant", "content": "hello", "timestamp": "2026-03-02T18:00:01"},
        ]
        loop.sessions.save(session)

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="/new")
        result = await loop._process_message(msg)

        assert result is not None
        assert result.content == "New session started. (Memory archival skipped.)"
        fresh = loop.sessions.get_or_create("feishu:chat123")
        assert fresh.messages == []

    @pytest.mark.asyncio
    async def test_new_clears_session_when_archival_succeeds(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._consolidate_memory = AsyncMock(return_value=True)

        session = loop.sessions.get_or_create("feishu:chat123")
        session.messages = [
            {"role": "user", "content": "hi", "timestamp": "2026-03-02T18:00:00"},
        ]
        loop.sessions.save(session)

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="/new")
        result = await loop._process_message(msg)

        assert result is not None
        assert result.content == "New session started."
        fresh = loop.sessions.get_or_create("feishu:chat123")
        assert fresh.messages == []


class TestMessageToolTurnTracking:

    def test_sent_in_turn_tracks_same_target(self) -> None:
        tool = MessageTool()
        tool.set_context("feishu", "chat1")
        assert not tool._sent_in_turn
        tool._sent_in_turn = True
        assert tool._sent_in_turn

    def test_start_turn_resets(self) -> None:
        tool = MessageTool()
        tool._sent_in_turn = True
        tool.start_turn()
        assert not tool._sent_in_turn


class TestFeishuReactionCleanup:

    def test_normalize_get_alias(self) -> None:
        channel = FeishuChannel(
            FeishuConfig(enabled=True, app_id="cli_xxx", app_secret="sec", react_emoji="GET"),
            MessageBus(),
        )
        assert channel._normalize_emoji(channel.config.react_emoji, channel._ACK_EMOJI) == "OnIt"

    @pytest.mark.asyncio
    async def test_send_clears_tracked_reaction_on_final_message(self) -> None:
        channel = FeishuChannel(
            FeishuConfig(enabled=True, app_id="cli_xxx", app_secret="sec"),
            MessageBus(),
        )
        channel._client = object()
        channel._pending_reactions["msg_1"] = ("react_1", "THUMBSUP")

        removed: list[tuple[str, str, str]] = []
        done_added: list[tuple[str, str]] = []
        channel._send_message_sync = lambda *args, **kwargs: True
        channel._remove_reaction_sync = (
            lambda message_id, reaction_id, emoji_type: (
                removed.append((message_id, reaction_id, emoji_type)) or True
            )
        )
        channel._add_reaction = AsyncMock(side_effect=lambda message_id, emoji: (
            done_added.append((message_id, emoji)) or "done_reaction_id"
        ))

        await channel.send(
            OutboundMessage(
                channel="feishu",
                chat_id="ou_user",
                content="done",
                metadata={"message_id": "msg_1"},
            )
        )

        assert removed == [("msg_1", "react_1", "THUMBSUP")]
        assert done_added == [("msg_1", "DONE")]
        assert "msg_1" not in channel._pending_reactions

    @pytest.mark.asyncio
    async def test_send_does_not_clear_reaction_for_progress_message(self) -> None:
        channel = FeishuChannel(
            FeishuConfig(enabled=True, app_id="cli_xxx", app_secret="sec"),
            MessageBus(),
        )
        channel._client = object()
        channel._pending_reactions["msg_1"] = ("react_1", "THUMBSUP")

        removed: list[tuple[str, str, str]] = []
        done_added: list[tuple[str, str]] = []
        channel._send_message_sync = lambda *args, **kwargs: True
        channel._remove_reaction_sync = (
            lambda message_id, reaction_id, emoji_type: (
                removed.append((message_id, reaction_id, emoji_type)) or True
            )
        )
        channel._add_reaction = AsyncMock(side_effect=lambda message_id, emoji: (
            done_added.append((message_id, emoji)) or "done_reaction_id"
        ))

        await channel.send(
            OutboundMessage(
                channel="feishu",
                chat_id="ou_user",
                content="thinking...",
                metadata={"message_id": "msg_1", "_progress": True},
            )
        )

        assert removed == []
        assert done_added == []
        assert channel._pending_reactions["msg_1"] == ("react_1", "THUMBSUP")
