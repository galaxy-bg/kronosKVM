from fastapi import APIRouter, Header, Request
from fastapi.responses import FileResponse

from backend.app.models.storage import FileOperation, StagingStorage
from backend.app.services.storage import (
    cancel_upload_task,
    delete_staged_file,
    staged_path,
    staging_info,
    store_upload,
    upload_tasks,
)

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("", response_model=StagingStorage)
def list_storage() -> StagingStorage:
    return staging_info()


@router.put("/files/{filename}", response_model=FileOperation)
async def upload_file(
    filename: str,
    request: Request,
    x_kronos_task_id: str = Header(default=None),
) -> FileOperation:
    return await store_upload(filename, request, x_kronos_task_id)


@router.get("/tasks")
def list_upload_tasks() -> dict:
    return {"tasks": upload_tasks()}


@router.delete("/tasks/{task_id}")
def cancel_task(task_id: str) -> dict:
    return cancel_upload_task(task_id)


@router.get("/files/{filename}")
def download_file(filename: str) -> FileResponse:
    path = staged_path(filename)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.delete("/files/{filename}", response_model=FileOperation)
def delete_file(filename: str) -> FileOperation:
    return delete_staged_file(filename)
