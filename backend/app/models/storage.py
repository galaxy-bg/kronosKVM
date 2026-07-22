from pydantic import BaseModel


class StagedFile(BaseModel):
    name: str
    size_bytes: int
    modified_at: str
    media_type: str


class StagingStorage(BaseModel):
    status: str
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    file_count: int
    files: list[StagedFile]


class FileOperation(BaseModel):
    status: str
    name: str
    size_bytes: int = 0
