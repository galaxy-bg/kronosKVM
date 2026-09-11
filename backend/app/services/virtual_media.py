import os
from pathlib import Path

from fastapi import HTTPException, status

from backend.app.models.storage import VirtualMediaStatus
from backend.app.services.storage import staged_path

STATE_PATH = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/var/lib/kronoskvm/state"))
REQUEST_PATH = STATE_PATH / "virtual-media-action"
STATUS_PATH = STATE_PATH / "virtual-media-status"
SUPPORTED_MEDIA = {".iso": "cdrom", ".img": "disk"}


def virtual_media_status() -> VirtualMediaStatus:
    if not STATUS_PATH.is_file():
        return VirtualMediaStatus(status="ejected")
    values: dict[str, str] = {}
    try:
        for line in STATUS_PATH.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"status", "filename", "media_type", "message"}:
                values[key] = value
    except OSError:
        return VirtualMediaStatus(
            status="unavailable",
            message="Unable to read virtual media state",
        )
    return VirtualMediaStatus(
        status=values.get("status", "ejected"),
        filename=values.get("filename") or None,
        media_type=values.get("media_type") or None,
        message=values.get("message") or None,
    )


def _stage_action(action: str, filename: str = "") -> VirtualMediaStatus:
    try:
        STATE_PATH.mkdir(parents=True, exist_ok=True)
        temporary = STATE_PATH / ".virtual-media-action.tmp"
        temporary.write_text(f"{action}\n{filename}\n", encoding="utf-8")
        temporary.replace(REQUEST_PATH)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Virtual media host helper is unavailable",
        ) from error
    return VirtualMediaStatus(
        status="attaching" if action == "attach" else "ejecting",
        filename=filename or None,
        media_type=SUPPORTED_MEDIA.get(Path(filename).suffix.lower()),
    )


def attach_virtual_media(filename: str) -> VirtualMediaStatus:
    path = staged_path(filename)
    media_type = SUPPORTED_MEDIA.get(path.suffix.lower())
    if media_type is None:
        raise HTTPException(status_code=400, detail="Only ISO and IMG files can be mounted")
    return _stage_action("attach", path.name)


def eject_virtual_media() -> VirtualMediaStatus:
    return _stage_action("eject")
