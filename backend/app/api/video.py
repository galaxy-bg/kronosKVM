from __future__ import annotations

import binascii
import re
import struct
import subprocess
import threading
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


def _run(*args: str, timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _timings() -> tuple[int, int] | None:
    result = _run("v4l2-ctl", "-d", str(VIDEO_DEVICE), "--query-dv-timings")
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


@router.get("/status")
def video_status() -> dict:
    timing = _timings() if VIDEO_DEVICE.exists() else None
    return {
        "ready": VIDEO_DEVICE.exists(),
        "signal": timing is not None,
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
    timing = _timings()
    if not timing:
        _capture_lock.release()
        raise HTTPException(status_code=503, detail="No HDMI signal detected")
    width, height = timing
    _run(
        "v4l2-ctl",
        "-d",
        str(VIDEO_DEVICE),
        "--set-dv-bt-timings=query",
        timeout=3,
    )
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
    with _stream_state_lock:
        _stream_process = process

    def frames():
        global _stream_process
        try:
            while process.stdout:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            _capture_lock.release()
            with _stream_state_lock:
                if _stream_process is process:
                    _stream_process = None

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=ffmpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
