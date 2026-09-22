from fastapi import APIRouter

from backend.app.api.services import _reconcile_results
from backend.app.services.tasks import clear_completed_tasks, task_list

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
def get_tasks() -> dict:
    _reconcile_results()
    return {"tasks": task_list(), "temporary": True}


@router.delete("/completed")
def clear_tasks() -> dict:
    return {"cleared": clear_completed_tasks()}
