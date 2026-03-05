import asyncio
import time

import pytest

from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


def test_add_job_rejects_unknown_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    with pytest.raises(ValueError, match="unknown timezone 'America/Vancovuer'"):
        service.add_job(
            name="tz typo",
            schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancovuer"),
            message="hello",
        )

    assert service.list_jobs(include_disabled=True) == []


def test_add_job_accepts_valid_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="tz ok",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancouver"),
        message="hello",
    )

    assert job.schedule.tz == "America/Vancouver"
    assert job.state.next_run_at_ms is not None


@pytest.mark.asyncio
async def test_running_service_honors_external_disable(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    called: list[str] = []

    async def on_job(job) -> None:
        called.append(job.id)

    service = CronService(store_path, on_job=on_job)
    job = service.add_job(
        name="external-disable",
        schedule=CronSchedule(kind="every", every_ms=200),
        message="hello",
    )
    await service.start()
    try:
        external = CronService(store_path)
        updated = external.enable_job(job.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False

        await asyncio.sleep(0.35)
        assert called == []
    finally:
        service.stop()


def test_add_at_job_with_small_past_skew_runs_immediately(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")
    now_ms = int(time.time() * 1000)

    job = service.add_job(
        name="past skew",
        schedule=CronSchedule(kind="at", at_ms=now_ms - 3000),
        message="hello",
    )

    assert job.state.next_run_at_ms is not None
    assert job.state.next_run_at_ms >= now_ms


def test_add_at_job_far_in_past_is_rejected(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")
    now_ms = int(time.time() * 1000)

    with pytest.raises(ValueError, match="at time is in the past"):
        service.add_job(
            name="too old",
            schedule=CronSchedule(kind="at", at_ms=now_ms - 120_000),
            message="hello",
        )


def test_add_job_persists_direct_message_payload_kind(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="direct",
        schedule=CronSchedule(kind="at", at_ms=int(time.time() * 1000) + 60_000),
        message="ping",
        payload_kind="direct_message",
        deliver=True,
        channel="feishu",
        to="ou_xxx",
        source_session_key="feishu:ou_xxx",
    )

    assert job.payload.kind == "direct_message"
    assert job.payload.deliver is True
    assert job.payload.source_session_key == "feishu:ou_xxx"

    reloaded = CronService(tmp_path / "cron" / "jobs.json")
    jobs = reloaded.list_jobs(include_disabled=True)
    assert len(jobs) == 1
    assert jobs[0].payload.source_session_key == "feishu:ou_xxx"
