"""On-demand SHA256 of staged files, with bounded memory and mutation checks."""
import hashlib
import os
import threading

from fastapi import HTTPException

from backend.app.services.storage import staged_path
from backend.app.services.tasks import update_task

HASH_LOCK = threading.Lock()


def signature(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def checksum(filename: str, task_id=None) -> dict:
    path = staged_path(filename)
    if not HASH_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another checksum is running; try again when it finishes")
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
            original = os.fstat(source.fileno())
            digest = hashlib.sha256()
            done = 0
            if task_id:
                update_task(task_id, title=f"SHA256: {filename}", bytes_total=original.st_size,
                            bytes_done=0, filename=filename)
            while chunk := source.read(4 * 1024 * 1024):
                digest.update(chunk)
                done += len(chunk)
                if task_id:
                    update_task(task_id, bytes_done=done,
                                progress=min(99, int(done * 100 / max(1, original.st_size))))
            if (signature(original) != signature(os.fstat(source.fileno()))
                    or signature(original) != signature(path.stat())):
                raise HTTPException(status_code=409, detail="File changed during checksum; calculate again")
            return {"filename": filename, "algorithm": "SHA256", "sha256": digest.hexdigest(),
                    "size_bytes": done}
    except OSError as error:
        raise HTTPException(status_code=409, detail="File could not be read or changed during checksum") from error
    finally:
        HASH_LOCK.release()
