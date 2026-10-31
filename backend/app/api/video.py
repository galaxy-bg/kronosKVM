from __future__ import annotations

import binascii
import logging
import re
import selectors
import struct
import subprocess
import threading
import time
import zlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

router = APIRouter(prefix="/api/v1/video", tags=["video"])

VIDEO_DEVICE = Path("/dev/video0")
_capture_lock = threading.Lock()
_stream_state_lock = threading.Lock()
_stream_process: Optional[subprocess.Popen] = None  # noqa: UP045
_latest_frame: bytes = b""
_latest_frame_at = 0.0
FRAME_TIMEOUT = 8.0
logger = logging.getLogger("kronoskvm.video")


@router.get("/latest.jpg")
def latest_video_frame() -> Response:
    with _stream_state_lock:
        frame, captured_at = _latest_frame, _latest_frame_at
    if not frame or time.monotonic() - captured_at > 3:
        raise HTTPException(status_code=503, detail="No current video frame; open the live stream")
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})



def _run(*args: str, timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _timings() -> tuple[int, int] | None:
    try:
        result = _run("v4l2-ctl", "-d", str(VIDEO_DEVICE), "--query-dv-timings")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"Active width:\s*(\d+).*?Active height:\s*(\d+)", output, re.S)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(
        ">I", binascii.crc32(body) & 0xFFFFFFFF
    )


def _encode_png(rgb: bytes, width: int, height: int) -> bytes:
    stride = width * 3
    scanlines = b"".join(
        b"\x00" + rgb[offset : offset + stride]
        for offset in range(0, len(rgb), stride)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=3))
        + _png_chunk(b"IEND", b"")
    )


def _cable_connected():
    try:
        result = _run("v4l2-ctl", "-d", str(VIDEO_DEVICE), "--get-ctrl=power_present", timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(rb"power_present:\s*(0x[0-9a-fA-F]+|[0-9]+)", result.stdout)
    return bool(int(match.group(1), 0)) if result.returncode == 0 and match else None


@router.get("/status")
def video_status() -> dict:
    timing = _timings() if VIDEO_DEVICE.exists() else None
    return {
        "ready": VIDEO_DEVICE.exists(),
        "signal": timing is not None,
        "cable_connected": _cable_connected() if VIDEO_DEVICE.exists() else None,
        "device": str(VIDEO_DEVICE),
        "width": timing[0] if timing else None,
        "height": timing[1] if timing else None,
    }


@router.get("/frame.png")
def video_frame() -> Response:
    if not VIDEO_DEVICE.exists():
        raise HTTPException(status_code=503, detail="HDMI capture device is unavailable")
    if not _capture_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="A video frame is already being captured")
    try:
        timing = _timings()
        if not timing:
            raise HTTPException(status_code=503, detail="No HDMI signal detected")
        width, height = timing
        _run(
            "v4l2-ctl",
            "-d",
            str(VIDEO_DEVICE),
            "--set-dv-bt-timings=query",
            timeout=3,
        )
        result = _run(
            "v4l2-ctl",
            "-d",
            str(VIDEO_DEVICE),
            f"--set-fmt-video=width={width},height={height},pixelformat=RGB3",
            "--stream-mmap=4",
            "--stream-skip=3",
            "--stream-count=1",
            "--stream-to=-",
            "--stream-poll",
            timeout=8,
        )
        expected = width * height * 3
        if result.returncode or len(result.stdout) < expected:
            raise HTTPException(status_code=503, detail="Unable to capture HDMI frame")
        png = _encode_png(result.stdout[:expected], width, height)
        return Response(
            png,
            media_type="image/png",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    finally:
        _capture_lock.release()


@router.get("/stream.mjpg")
def video_stream() -> StreamingResponse:
    global _stream_process
    if not VIDEO_DEVICE.exists():
        raise HTTPException(status_code=503, detail="HDMI capture device is unavailable")
    with _stream_state_lock:
        previous_process = _stream_process
    if previous_process and previous_process.poll() is None:
        previous_process.terminate()
        try:
            previous_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            previous_process.kill()
    if not _capture_lock.acquire(timeout=3):
        raise HTTPException(status_code=429, detail="Video capture is already active")
    try:
        timing = _timings()
        if not timing:
            raise HTTPException(status_code=503, detail="No HDMI signal detected")
        width, height = timing
        configured = _run(
            "v4l2-ctl",
            "-d",
            str(VIDEO_DEVICE),
            "--set-dv-bt-timings=query",
            timeout=3,
        )
        if configured.returncode:
            raise HTTPException(503, "HDMI timing configuration failed; retry the connection")
        process = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
                "-f",
                "v4l2",
                "-input_format",
                "uyvy422",
                "-video_size",
                f"{width}x{height}",
                "-framerate",
                "15",
                "-i",
                str(VIDEO_DEVICE),
                "-an",
                "-vf",
                "fps=12",
                "-c:v",
                "mjpeg",
                "-q:v",
                "7",
                "-f",
                "mpjpeg",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except BaseException as error:
        _capture_lock.release()
        if isinstance(error, (OSError, subprocess.SubprocessError)):
            raise HTTPException(503, "HDMI capture could not start; retry the connection") from None
        raise
    with _stream_state_lock:
        _stream_process = process

    def frames():
        global _stream_process, _latest_frame, _latest_frame_at
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                yield from read_frames(selector)
        finally:
            try:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                logger.warning("HDMI encoder cleanup failed; capture lock released")
            finally:
                _capture_lock.release()
                with _stream_state_lock:
                    if _stream_process is process:
                        _stream_process = None
                        _latest_frame = b""
                        _latest_frame_at = 0.0

    def read_frames(selector):
        global _latest_frame, _latest_frame_at
        pending = bytearray()
        last_frame_at = time.monotonic()
        while process.stdout:
            if time.monotonic() - last_frame_at >= FRAME_TIMEOUT:
                logger.warning("HDMI stream stalled; releasing capture for reconnect")
                break
            if not selector.select(timeout=1):
                continue
            chunk = process.stdout.read1(64 * 1024)
            if not chunk:
                break
            pending.extend(chunk)
            while True:
                start = pending.find(b"\xff\xd8")
                if start < 0:
                    pending[:] = pending[-1:]
                    break
                end = pending.find(b"\xff\xd9", start + 2)
                if end < 0:
                    del pending[:start]
                    break
                frame = bytes(pending[start:end + 2])
                del pending[:end + 2]
                with _stream_state_lock:
                    _latest_frame = frame
                    _latest_frame_at = time.monotonic()
                    last_frame_at = _latest_frame_at
            if len(pending) > 16 * 1024 * 1024:
                pending.clear()
            yield chunk

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=ffmpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
