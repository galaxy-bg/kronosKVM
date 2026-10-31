import asyncio
import os
import subprocess
import threading
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.app.api import video


@pytest.fixture
def capture(monkeypatch):
    lock = threading.Lock()
    monkeypatch.setattr(video, "_capture_lock", lock)
    monkeypatch.setattr(video, "_stream_process", None)
    monkeypatch.setattr(
        video, "VIDEO_DEVICE", Mock(exists=lambda: True, __str__=lambda s: "/dev/video0")
    )
    monkeypatch.setattr(video, "_timings", lambda: (1024, 768))
    monkeypatch.setattr(video, "_run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b""))
    return lock


@pytest.mark.parametrize("stage", ["timings", "configuration", "encoder"])
def test_failed_stream_start_always_releases_capture(capture, monkeypatch, stage):
    if stage == "timings":
        monkeypatch.setattr(
            video, "_timings", Mock(side_effect=subprocess.TimeoutExpired("v4l2", 5))
        )
    elif stage == "configuration":
        monkeypatch.setattr(video, "_run", Mock(side_effect=subprocess.TimeoutExpired("v4l2", 3)))
    else:
        monkeypatch.setattr(
            video.subprocess, "Popen", Mock(side_effect=OSError("encoder unavailable"))
        )
    with pytest.raises(HTTPException) as error:
        video.video_stream()
    assert error.value.status_code == 503
    assert not capture.locked()


def test_timing_query_timeout_is_treated_as_no_signal(monkeypatch):
    monkeypatch.setattr(video, "_run", Mock(side_effect=subprocess.TimeoutExpired("v4l2", 5)))
    assert video._timings() is None


def test_stalled_encoder_is_stopped_and_lock_is_reusable(capture, monkeypatch):
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as stream:
        process = Mock(stdout=stream)
        monkeypatch.setattr(video.subprocess, "Popen", lambda *a, **kw: process)
        monkeypatch.setattr(video, "FRAME_TIMEOUT", -1)
        response = video.video_stream()
        assert capture.locked()

        async def consume():
            return [chunk async for chunk in response.body_iterator]

        assert asyncio.run(consume()) == []
        process.terminate.assert_called_once()
        assert not capture.locked()
        assert video._stream_process is None
    os.close(write_fd)


def test_encoder_cleanup_failure_does_not_keep_lock(capture, monkeypatch):
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as stream:
        process = Mock(stdout=stream)
        process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", 2)
        monkeypatch.setattr(video.subprocess, "Popen", lambda *a, **kw: process)
        monkeypatch.setattr(video, "FRAME_TIMEOUT", -1)
        response = video.video_stream()

        async def consume():
            return [chunk async for chunk in response.body_iterator]

        asyncio.run(consume())
        process.kill.assert_called_once()
        assert not capture.locked()
    os.close(write_fd)


def test_status_reports_cable_detection_independently(capture, monkeypatch):
    monkeypatch.setattr(video, "_timings", lambda: None)
    monkeypatch.setattr(
        video, "_run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b"power_present: 0\n")
    )
    status = video.video_status()
    assert status["ready"] and not status["signal"] and status["cable_connected"] is False
