from __future__ import annotations

import time

import pytest

from nanobot.agent.tools.cron import CronTool
from nanobot.cron.service import CronService


@pytest.mark.asyncio
async def test_cron_tool_at_creates_direct_message_job(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")
    tool = CronTool(service)
    tool.set_context("feishu", "ou_test")

    at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 120))
    result = await tool.execute(action="add", message="hello", at=at)

    assert "Created job" in result
    jobs = service.list_jobs(include_disabled=True)
    assert len(jobs) == 1
    assert jobs[0].payload.kind == "direct_message"
    assert jobs[0].payload.deliver is True
    assert jobs[0].payload.channel == "feishu"
    assert jobs[0].payload.to == "ou_test"
    assert jobs[0].payload.source_session_key == "feishu:ou_test"


@pytest.mark.asyncio
async def test_cron_tool_every_creates_agent_turn_job(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")
    tool = CronTool(service)
    tool.set_context("feishu", "ou_test")

    result = await tool.execute(action="add", message="check status", every_seconds=60)

    assert "Created job" in result
    jobs = service.list_jobs(include_disabled=True)
    assert len(jobs) == 1
    assert jobs[0].payload.kind == "agent_turn"
    assert jobs[0].payload.source_session_key == "feishu:ou_test"
