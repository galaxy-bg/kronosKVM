import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.app.logging import audit

TASKS: dict[str, dict] = {}
TASKS_LOCK = threading.Lock()
MAX_TASKS = 500
TERMINAL_STATES = {"successful", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot(task: dict) -> dict:
    return dict(task)


def start_task(
    operation: str,
    title: str,
    task_id: Optional[str] = None,
    detail: Optional[str] = None,
    source: str = "application",
) -> dict:
    identifier = task_id or str(uuid.uuid4())
    now = _now()
    task = {
        "id": identifier,
        "operation": operation,
        "title": title,
        "detail": detail,
        "source": source,
        "status": "running",
        "progress": 0,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "error": None,
    }
    with TASKS_LOCK:
        TASKS[identifier] = task
        if len(TASKS) > MAX_TASKS:
            oldest = sorted(TASKS.values(), key=lambda item: item["created_at"])
            for expired in oldest[: len(TASKS) - MAX_TASKS]:
                TASKS.pop(expired["id"], None)
    audit("task.started", task_id=identifier, operation=operation, title=title, source=source)
    return _snapshot(task)


def update_task(task_id: str, **values: object) -> Optional[dict]:
    with TASKS_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            return None
        old_status = task["status"]
        task.update(values)
        task["updated_at"] = _now()
        if task["status"] in TERMINAL_STATES and not task["completed_at"]:
            task["completed_at"] = task["updated_at"]
        snapshot = _snapshot(task)
    if snapshot["status"] != old_status or snapshot["status"] in TERMINAL_STATES:
        audit(
            "task.status.changed",
            task_id=task_id,
            operation=snapshot["operation"],
            status=snapshot["status"],
            error=snapshot.get("error"),
        )
    return snapshot


def finish_task(task_id: str, successful: bool, error: Optional[str] = None) -> Optional[dict]:
    return update_task(
        task_id,
        status="successful" if successful else "failed",
        progress=100 if successful else 0,
        error=error,
    )


def task_list() -> list[dict]:
    with TASKS_LOCK:
        tasks = [_snapshot(task) for task in TASKS.values()]
    return sorted(tasks, key=lambda item: item["created_at"], reverse=True)


def clear_completed_tasks() -> int:
    with TASKS_LOCK:
        identifiers = [
            task_id for task_id, task in TASKS.items() if task["status"] in TERMINAL_STATES
        ]
        for task_id in identifiers:
            TASKS.pop(task_id, None)
    if identifiers:
        audit("task.history.cleared", count=len(identifiers))
    return len(identifiers)
