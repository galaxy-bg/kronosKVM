from __future__ import annotations

import asyncio
import os
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.services import external_storage, storage

router = APIRouter(prefix="/api/v1/external-storage", tags=["storage"])


class ImportFile(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


@router.get("")
def list_external_storage() -> dict:
    return external_storage.inventory()


@router.get("/{device}/files")
def list_external_files(device: str, path: str = Query(default="", max_length=2048)) -> dict:
    return external_storage.browse(device, path)


@router.get("/{device}/download")
def download_external_file(device: str, path: str = Query(max_length=2048)) -> StreamingResponse:
    fd = external_storage.open_entry(device, path)
    file = os.fdopen(fd, "rb")

    def chunks():
        try:
            while chunk := file.read(1024 * 1024):
                yield chunk
        finally:
            file.close()

    return StreamingResponse(
        chunks(),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(os.fstat(fd).st_size),
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(PurePosixPath(path).name),
        },
    )


@router.post("/{device}/import")
async def import_external_file(device: str, value: ImportFile) -> dict:
    fd = external_storage.open_entry(device, value.path)
    with os.fdopen(fd, "rb") as file:
        size = os.fstat(fd).st_size
        remaining = size

        async def receive():
            nonlocal remaining
            chunk = await asyncio.to_thread(file.read, min(1024 * 1024, remaining))
            if not chunk and remaining:
                raise OSError("USB file ended before the expected size")
            remaining -= len(chunk)
            return {"type": "http.request", "body": chunk, "more_body": remaining > 0}

        request = Request(
            {
                "type": "http",
                "headers": [
                    (b"content-length", str(size).encode()),
                ],
            },
            receive=receive,
        )
        result = await storage.store_upload(
            PurePosixPath(value.path).name, request, overwrite=False
        )
        return result.model_dump()
