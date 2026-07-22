import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request, status

from backend.app.models.storage import FileOperation, StagedFile, StagingStorage

STORAGE_PATH = Path(os.environ.get("KRONOSKVM_STORAGE_PATH", "/var/lib/kronoskvm/storage"))
MAX_UPLOAD_BYTES = int(os.environ.get("KRONOSKVM_MAX_UPLOAD_BYTES", str(16 * 1024**3)))
MIN_FREE_BYTES = int(os.environ.get("KRONOSKVM_STORAGE_RESERVE_BYTES", str(1024**3)))


def _safe_name(filename: str) -> str:
    name = filename.strip()
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or len(name.encode("utf-8")) > 180
        or name.startswith(".")
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return name


def _storage_root() -> Path:
    try:
        STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Staging storage is unavailable",
        ) from error
    return STORAGE_PATH


def staging_info() -> StagingStorage:
    root = _storage_root()
    usage = shutil.disk_usage(root)
    files = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError as error:
        raise HTTPException(status_code=503, detail="Unable to read staging storage") from error
    for path in entries:
        if path.name.endswith(".uploading") or path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        files.append(
            StagedFile(
                name=path.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
        )
    return StagingStorage(
        status="ready",
        path=str(root),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        file_count=len(files),
        files=files,
    )


def staged_path(filename: str) -> Path:
    path = _storage_root() / _safe_name(filename)
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return path


async def store_upload(filename: str, request: Request) -> FileOperation:
    name = _safe_name(filename)
    root = _storage_root()
    expected = request.headers.get("content-length")
    if expected:
        try:
            expected_bytes = int(expected)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from error
        if expected_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds upload limit")
        if expected_bytes > max(0, shutil.disk_usage(root).free - MIN_FREE_BYTES):
            raise HTTPException(status_code=507, detail="Not enough staging storage space")

    target = root / name
    temporary = root / f".{name}.uploading"
    written = 0
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds upload limit")
                if chunk:
                    output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="Empty uploads are not accepted")
        temporary.replace(target)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=507, detail="Unable to store uploaded file") from error
    return FileOperation(status="stored", name=name, size_bytes=written)


def delete_staged_file(filename: str) -> FileOperation:
    path = staged_path(filename)
    size = path.stat().st_size
    try:
        path.unlink()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to delete staged file") from error
    return FileOperation(status="deleted", name=path.name, size_bytes=size)
