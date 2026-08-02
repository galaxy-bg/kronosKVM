from fastapi import APIRouter, Header, Request
from fastapi.responses import FileResponse

from backend.app.models.storage import (
    FileOperation,
    StagingStorage,
    VirtualMediaRequest,
    VirtualMediaStatus,
)
from backend.app.services.storage import (
    cancel_upload_task,
    delete_staged_file,
    staged_path,
    staging_info,
    store_upload,
    upload_tasks,
)
from backend.app.services.virtual_media import (
    attach_virtual_media,
    eject_virtual_media,
    virtual_media_status,
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


@router.get("/virtual-media", response_model=VirtualMediaStatus)
def get_virtual_media() -> VirtualMediaStatus:
    return virtual_media_status()


@router.post("/virtual-media", response_model=VirtualMediaStatus, status_code=202)
def mount_virtual_media(request: VirtualMediaRequest) -> VirtualMediaStatus:
    return attach_virtual_media(request.filename)


@router.delete("/virtual-media", response_model=VirtualMediaStatus, status_code=202)
def unmount_virtual_media() -> VirtualMediaStatus:
    return eject_virtual_media()


@router.get("/files/{filename}")
def download_file(filename: str) -> FileResponse:
    path = staged_path(filename)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.delete("/files/{filename}", response_model=FileOperation)
def delete_file(filename: str) -> FileOperation:
    return delete_staged_file(filename)
