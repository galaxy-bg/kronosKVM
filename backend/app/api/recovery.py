"""Manage the shared, read-only recovery publication directory."""
import csv
import hashlib
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app.hardware.recovery_history import history
from backend.app.services import storage
from backend.app.services.virtual_media import virtual_media_status

router = APIRouter(prefix="/api/v1/recovery", tags=["recovery"])
LOCK = threading.Lock()
ADDRESS = "192.168.34.100"
NETWORK_STATE = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state")) / "recovery-network.json"


@router.get("/network/history")
def network_history():
    return {"entries": history(NETWORK_STATE.with_name("recovery-history.sqlite3"))}


@router.get("/network/history/download")
def download_network_history():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Observed (UTC)", "Device", "IP address", "MAC", "Lease expires (UTC)"])

    def timestamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else "Permanent"

    def safe_cell(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

    for entry in network_history()["entries"]:
        writer.writerow([
            timestamp(entry["observed_at"]), safe_cell(entry["hostname"]),
            safe_cell(entry["ip"]), safe_cell(entry["mac"]),
            timestamp(entry.get("expires_at", 0)),
        ])
    return Response(
        "\ufeff" + output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="recovery-device-history.csv"'},
    )


@router.delete("/network/history")
def clear_network_history():
    history(NETWORK_STATE.with_name("recovery-history.sqlite3"), clear=True)
    return {"status": "cleared"}


class PublishFile(BaseModel):
    filename: str
    folder: str = ""


def recovery_root() -> Path:
    root = storage._storage_root() / "recovery"
    if root.is_symlink():
        raise HTTPException(status_code=400, detail="Invalid recovery directory")
    root.mkdir(exist_ok=True)
    return root


def recovery_path(value: str) -> Path:
    parts = value.split("/")
    if not parts or any(storage._safe_name(part) != part for part in parts):
        raise HTTPException(status_code=400, detail="Invalid recovery path")
    root = recovery_root()
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise HTTPException(status_code=400, detail="Symbolic links are not supported")
    if not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(status_code=400, detail="Invalid recovery path")
    return path


@router.get("")
def list_recovery() -> dict:
    root = recovery_root()
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file() or name.startswith("."):
                continue
            relative = path.relative_to(root).as_posix()
            files.append({
                "path": relative,
                "size_bytes": path.stat().st_size,
                "http_url": f"http://{ADDRESS}:8080/{quote(relative)}",
                "tftp_path": relative,
                "ftp_url": f"ftp://{ADDRESS}/{quote(relative)}",
            })
    return {"address": ADDRESS, "files": sorted(files, key=lambda item: item["path"])}


@router.post("/files", status_code=201)
def publish_file(value: PublishFile) -> dict:
    with LOCK:
        source = storage.staged_path(value.filename)
        media = virtual_media_status()
        if media.filename == source.name and media.status != "ejected":
            raise HTTPException(status_code=409, detail="Eject virtual media before moving it")
        relative = f"{value.folder}/{source.name}" if value.folder else source.name
        target = recovery_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Link/unlink is an atomic no-overwrite move on this shared filesystem.
            os.link(source, target)
            source.unlink()
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail="Recovery file already exists") from error
        return {"path": relative, "status": "published"}


@router.get("/checksum/{path:path}")
def checksum(path: str) -> dict:
    target = recovery_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Recovery file not found")
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": path, "sha256": digest.hexdigest()}


@router.post("/restore/{path:path}")
def restore_file(path: str) -> dict:
    with LOCK:
        source = recovery_path(path)
        if not source.is_file():
            raise HTTPException(status_code=404, detail="Recovery file not found")
        target = storage._storage_root() / source.name
        try:
            os.link(source, target)
            source.unlink()
        except FileExistsError as error:
            raise HTTPException(status_code=409, detail="Staging file already exists") from error
        return {"status": "restored", "name": target.name}


@router.get("/network")
def recovery_network() -> dict:
    try:
        value = json.loads(NETWORK_STATE.read_text(encoding="utf-8"))
        value["stale"] = time.time() - value["updated_at"] > 20
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return {"stale": True, "ports": [], "leases": [], "updated_at": None}
