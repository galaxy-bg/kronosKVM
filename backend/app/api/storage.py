from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from backend.app.models.storage import FileOperation, StagingStorage
from backend.app.services.storage import (
    delete_staged_file,
    staged_path,
    staging_info,
    store_upload,
)

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("", response_model=StagingStorage)
def list_storage() -> StagingStorage:
    return staging_info()


@router.put("/files/{filename}", response_model=FileOperation)
async def upload_file(filename: str, request: Request) -> FileOperation:
    return await store_upload(filename, request)


@router.get("/files/{filename}")
def download_file(filename: str) -> FileResponse:
    path = staged_path(filename)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.delete("/files/{filename}", response_model=FileOperation)
def delete_file(filename: str) -> FileOperation:
    return delete_staged_file(filename)
