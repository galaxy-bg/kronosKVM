import mimetypes
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request, status

from backend.app.models.storage import FileOperation, StagedFile, StagingStorage
from backend.app.services.tasks import update_task as update_global_task

STORAGE_PATH = Path(os.environ.get("KRONOSKVM_STORAGE_PATH", "/var/lib/kronoskvm/storage"))
MAX_UPLOAD_BYTES = int(os.environ.get("KRONOSKVM_MAX_UPLOAD_BYTES", str(16 * 1024**3)))
STORAGE_CAPACITY_BYTES = int(
    os.environ.get("KRONOSKVM_STORAGE_CAPACITY_BYTES", str(32 * 1024**3))
)
MIN_FREE_BYTES = int(os.environ.get("KRONOSKVM_STORAGE_RESERVE_BYTES", str(10 * 1024**3)))
REQUIRE_MARKER = os.environ.get("KRONOSKVM_STORAGE_REQUIRE_MARKER", "0") == "1"
MEDIA_MARKER = ".kronoskvm-storage"
POOL_ID = os.environ.get("KRONOSKVM_STORAGE_POOL_ID", "internal")
POOL_LABEL = os.environ.get("KRONOSKVM_STORAGE_LABEL", "Internal SD · 32G")
STORAGE_TYPE = os.environ.get("KRONOSKVM_STORAGE_TYPE", "internal")
UPLOAD_TASKS: dict[str, dict] = {}
UPLOAD_TASKS_LOCK = threading.Lock()


def _task_snapshot(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "cancel_requested"}


def upload_tasks() -> list[dict]:
    with UPLOAD_TASKS_LOCK:
        tasks = [_task_snapshot(task) for task in UPLOAD_TASKS.values()]
    return sorted(tasks, key=lambda item: item["created_at"], reverse=True)


def cancel_upload_task(task_id: str) -> dict:
    with UPLOAD_TASKS_LOCK:
        task = UPLOAD_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Upload task not found")
        if task["status"] in {"queued", "running"}:
            task["cancel_requested"] = True
            task["status"] = "cancelling"
        return _task_snapshot(task)


def _update_task(task_id: str, **values: object) -> None:
    with UPLOAD_TASKS_LOCK:
        if task_id in UPLOAD_TASKS:
            UPLOAD_TASKS[task_id].update(values)
    global_values = dict(values)
    status_value = global_values.get("status")
    if status_value == "completed":
        global_values["status"] = "successful"
    elif status_value == "cancelled":
        global_values["status"] = "cancelled"
    global_values.pop("bytes_done", None)
    global_values.pop("updated_at", None)
    update_global_task(task_id, **global_values)


def _task_cancelled(task_id: str) -> bool:
    with UPLOAD_TASKS_LOCK:
        return bool(UPLOAD_TASKS.get(task_id, {}).get("cancel_requested"))


def _active_upload_reservations() -> tuple[int, int]:
    with UPLOAD_TASKS_LOCK:
        active = [
            task for task in UPLOAD_TASKS.values()
            if task["status"] in {"running", "cancelling"}
        ]
        quota_reserved = sum(task["bytes_total"] for task in active)
        physical_reserved = sum(
            max(0, task["bytes_total"] - task["bytes_done"]) for task in active
        )
    return quota_reserved, physical_reserved


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
        or any(ord(character) < 32 for character in name)
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
    if REQUIRE_MARKER and not (STORAGE_PATH / MEDIA_MARKER).is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Removable staging media is not mounted or initialized",
        )
    return STORAGE_PATH


def cleanup_incomplete_uploads() -> list[str]:
    """Remove upload fragments left behind by a crash or power loss."""
    try:
        root = _storage_root()
    except HTTPException:
        return []
    removed = []
    for path in root.glob(".*.uploading"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return removed


def _managed_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.iterdir()
        if path.name != MEDIA_MARKER
        and not path.name.endswith(".uploading")
        and not path.is_symlink()
        and path.is_file()
    ]


def _managed_bytes(root: Path, exclude: Optional[Path] = None) -> int:
    return sum(path.stat().st_size for path in _managed_files(root) if path != exclude)


def staging_info() -> StagingStorage:
    try:
        root = _storage_root()
    except HTTPException as error:
        if error.status_code != status.HTTP_503_SERVICE_UNAVAILABLE:
            raise
        return StagingStorage(
            status="media_missing",
            path=str(STORAGE_PATH),
            pool_id=POOL_ID,
            label=POOL_LABEL,
            storage_type=STORAGE_TYPE,
            total_bytes=0,
            used_bytes=0,
            free_bytes=0,
            system_reserve_bytes=MIN_FREE_BYTES,
            file_count=0,
            files=[],
        )
    usage = shutil.disk_usage(root)
    files = []
    try:
        entries = sorted(_managed_files(root), key=lambda item: item.name.lower())
    except OSError as error:
        raise HTTPException(status_code=503, detail="Unable to read staging storage") from error
    for path in entries:
        stat = path.stat()
        files.append(
            StagedFile(
                name=path.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
        )
    managed_bytes = sum(item.size_bytes for item in files)
    effective_free = min(
        max(0, STORAGE_CAPACITY_BYTES - managed_bytes),
        max(0, usage.free - MIN_FREE_BYTES),
    )
    return StagingStorage(
        status="ready",
        path=str(root),
        pool_id=POOL_ID,
        label=POOL_LABEL,
        storage_type=STORAGE_TYPE,
        total_bytes=STORAGE_CAPACITY_BYTES,
        used_bytes=managed_bytes,
        free_bytes=effective_free,
        system_reserve_bytes=MIN_FREE_BYTES,
        file_count=len(files),
        files=files,
    )


def staged_path(filename: str) -> Path:
    path = _storage_root() / _safe_name(filename)
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return path


async def store_upload(
    filename: str,
    request: Request,
    requested_task_id: Optional[str] = None,
) -> FileOperation:
    name = _safe_name(filename)
    try:
        task_id = str(uuid.UUID(requested_task_id)) if requested_task_id else str(uuid.uuid4())
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid upload task ID") from error
    with UPLOAD_TASKS_LOCK:
        duplicate = any(
            task["name"] == name and task["status"] in {"running", "cancelling"}
            for task in UPLOAD_TASKS.values()
        )
    if duplicate:
        raise HTTPException(status_code=409, detail="A task is already uploading this file")
    root = _storage_root()
    expected = request.headers.get("content-length")
    expected_bytes = 0
    target = root / name
    quota_reserved, physical_reserved = _active_upload_reservations()
    quota_available = max(
        0, STORAGE_CAPACITY_BYTES - _managed_bytes(root, exclude=target) - quota_reserved
    )
    physical_available = max(
        0, shutil.disk_usage(root).free - MIN_FREE_BYTES - physical_reserved
    )
    available = min(quota_available, physical_available)
    if expected:
        try:
            expected_bytes = int(expected)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from error
        if expected_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds upload limit")
        if expected_bytes > available:
            raise HTTPException(status_code=507, detail="Not enough staging storage space")

    temporary = root / f".{name}.{task_id}.uploading"
    written = 0
    completed = False
    now = datetime.now(timezone.utc).isoformat()
    with UPLOAD_TASKS_LOCK:
        UPLOAD_TASKS[task_id] = {
            "id": task_id,
            "type": "storage_upload",
            "name": name,
            "status": "running",
            "progress": 0,
            "bytes_done": 0,
            "bytes_total": expected_bytes,
            "created_at": now,
            "updated_at": now,
            "error": None,
            "cancel_requested": False,
        }
    try:
        with temporary.open("wb") as output:
            async for chunk in request.stream():
                if _task_cancelled(task_id):
                    raise HTTPException(status_code=409, detail="Upload task cancelled")
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds upload limit")
                if written > available:
                    raise HTTPException(status_code=507, detail="Internal staging quota exceeded")
                if chunk:
                    output.write(chunk)
                progress = round(written / expected_bytes * 100) if expected_bytes else 0
                _update_task(
                    task_id,
                    progress=min(progress, 99),
                    bytes_done=written,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
        if written == 0:
            raise HTTPException(status_code=400, detail="Empty uploads are not accepted")
        temporary.replace(target)
        completed = True
        _update_task(
            task_id,
            status="completed",
            progress=100,
            bytes_done=written,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    except HTTPException as error:
        _update_task(
            task_id,
            status="cancelled" if error.status_code == 409 else "failed",
            error=error.detail,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        raise
    except OSError as error:
        _update_task(
            task_id,
            status="failed",
            error="Unable to store uploaded file",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        raise HTTPException(status_code=507, detail="Unable to store uploaded file") from error
    except Exception:
        _update_task(
            task_id,
            status="cancelled" if _task_cancelled(task_id) else "failed",
            error="Upload connection interrupted",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        raise
    finally:
        if not completed:
            temporary.unlink(missing_ok=True)
    return FileOperation(status="stored", name=name, size_bytes=written)


def delete_staged_file(filename: str) -> FileOperation:
    path = staged_path(filename)
    from backend.app.services.virtual_media import virtual_media_status

    media = virtual_media_status()
    if media.status in {"attaching", "attached"} and media.filename == path.name:
        raise HTTPException(status_code=409, detail="Eject virtual media before deleting it")
    size = path.stat().st_size
    try:
        path.unlink()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to delete staged file") from error
    return FileOperation(status="deleted", name=path.name, size_bytes=size)
