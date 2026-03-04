from pathlib import Path

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse


class _SwitchingProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key="sk-or-test", api_base="https://openrouter.ai/api/v1")
        self.called_models: list[str] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        self.called_models.append(model or "")
        if model == "simple-model":
            return LLMResponse(content="Temporary model failure", finish_reason="error")
        return LLMResponse(content="done")

    def get_default_model(self) -> str:
        return "complex-model"


def _make_loop(tmp_path: Path, *, model_routing: str = "auto") -> AgentLoop:
    return AgentLoop(
        bus=MessageBus(),
        provider=_SwitchingProvider(),
        workspace=tmp_path,
        simple_model="simple-model",
        complex_model="complex-model",
        model_routing=model_routing,
        memory_window=10,
    )


def test_pick_initial_model_by_routing_mode(tmp_path: Path):
    loop = _make_loop(tmp_path, model_routing="simple")
    assert loop._pick_initial_model("请做一个复杂架构设计") == "simple-model"

    loop = _make_loop(tmp_path, model_routing="complex")
    assert loop._pick_initial_model("just summarize this text") == "complex-model"


def test_pick_initial_model_auto_uses_complex_for_complex_prompts(tmp_path: Path):
    loop = _make_loop(tmp_path, model_routing="auto")
    assert loop._pick_initial_model("请做一个系统架构设计并分析 tradeoff") == "complex-model"
    assert loop._pick_initial_model("帮我总结这段话") == "simple-model"


@pytest.mark.asyncio
async def test_auto_upgrade_from_simple_to_complex_on_provider_error(tmp_path: Path):
    loop = _make_loop(tmp_path, model_routing="auto")
    provider = loop.provider

    final, _tools, _messages = await loop._run_agent_loop(
        initial_messages=[
            {"role": "system", "content": "You are a test assistant."},
            {"role": "user", "content": "Summarize this"},
        ],
        user_message="Summarize this",
    )

    assert final == "done"
    assert provider.called_models[:2] == ["simple-model", "complex-model"]
