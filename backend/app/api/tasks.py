from fastapi import APIRouter

from backend.app.services.tasks import clear_completed_tasks, task_list

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
def get_tasks() -> dict:
    return {"tasks": task_list(), "temporary": True}


@router.delete("/completed")
def clear_tasks() -> dict:
    return {"cleared": clear_completed_tasks()}
