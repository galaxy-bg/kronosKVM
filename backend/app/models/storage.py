from typing import Optional

from pydantic import BaseModel


class StagedFile(BaseModel):
    name: str
    size_bytes: int
    modified_at: str
    media_type: str


class StagingStorage(BaseModel):
    status: str
    path: str
    pool_id: str = "internal"
    label: str = "Internal SD"
    storage_type: str = "internal"
    total_bytes: int
    used_bytes: int
    free_bytes: int
    system_reserve_bytes: int = 0
    file_count: int
    files: list[StagedFile]


class FileOperation(BaseModel):
    status: str
    name: str
    size_bytes: int = 0


class VirtualMediaRequest(BaseModel):
    filename: str


class VirtualMediaStatus(BaseModel):
    status: str = "ejected"
    filename: Optional[str] = None
    media_type: Optional[str] = None
    message: Optional[str] = None
