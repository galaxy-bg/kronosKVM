import json
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.services.tasks import finish_task, start_task

router = APIRouter(prefix="/api/v1/services", tags=["services"])
STATE_PATH = Path(os.environ.get("KRONOSKVM_STATE_PATH", "/state"))
REQUEST_PATH = STATE_PATH / "service-action"
STATUS_PATH = STATE_PATH / "service-status.json"
RESULT_PATTERN = re.compile(r"^service-result-([0-9a-f-]{36})\.json$")
LOG_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")

CATALOG = (
    ("containers", "Application Containers", "API and web management plane", True),
    ("docker", "Container Runtime", "Docker engine", True),
    ("management_ap", "Wi-Fi Management AP", "KDX InfraBox recovery access point", True),
    ("dnsmasq", "DHCP and DNS", "Management AP address services", True),
    ("networkmanager", "Network Manager", "Ethernet and Wi-Fi configuration", False),
    ("ssh", "SSH Management", "Secure host administration", True),
    ("wittypi", "Witty Pi", "RTC and power-management daemon", True),
    ("tftp", "TFTP Recovery", "Recovery firmware and PXE transfer service", False),
    ("recovery_http", "HTTP Recovery", "Recovery file distribution service", False),
)


class ServiceAction(BaseModel):
    confirmed: bool = False


def _read_status() -> dict:
    try:
        value = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _reconcile_results() -> None:
    try:
        paths = list(STATE_PATH.iterdir())
    except OSError:
        return
    for path in paths:
        match = RESULT_PATTERN.fullmatch(path.name)
        if not match:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            task_id = match.group(1)
            finished = finish_task(task_id, bool(value.get("successful")), value.get("error"))
            if finished is None:
                service_id = str(value.get("service", "service"))
                label = next((item[1] for item in CATALOG if item[0] == service_id), service_id)
                recovered = start_task(
                    f"service.{value.get('action', 'restart')}",
                    f"Restart {label}",
                    task_id=task_id,
                    source="services",
                )
                finish_task(recovered["id"], bool(value.get("successful")), value.get("error"))
            path.unlink()
        except (OSError, json.JSONDecodeError):
            continue


def _queue(service_id: str, action: str, title: str) -> dict:
    task = start_task(f"service.{action}", title, source="services")
    try:
        STATE_PATH.mkdir(parents=True, exist_ok=True)
        pending = STATE_PATH / ".service-action.tmp"
        pending.write_text(
            f"service={service_id}\naction={action}\ntask_id={task['id']}\n",
            encoding="ascii",
        )
        pending.replace(REQUEST_PATH)
    except OSError as error:
        finish_task(task["id"], False, "Service host helper is unavailable")
        raise HTTPException(status_code=503, detail="Service host helper is unavailable") from error
    return task


@router.get("")
def service_list() -> dict:
    _reconcile_results()
    status_data = _read_status()
    live = status_data.get("services", {})
    services = []
    for service_id, name, description, restartable in CATALOG:
        state = live.get(service_id, {})
        services.append(
            {
                "id": service_id,
                "name": name,
                "description": description,
                "state": state.get("state", "unknown"),
                "detail": state.get("detail"),
                "restartable": restartable and state.get("state") != "not_installed",
            }
        )
    return {"services": services, "updated_at": status_data.get("updated_at")}


@router.get("/{service_id}/logs")
def service_logs(service_id: str) -> dict:
    allowed = {item[0]: item for item in CATALOG}
    if service_id not in allowed or not LOG_ID_PATTERN.fullmatch(service_id):
        raise HTTPException(status_code=404, detail="Unknown service")
    path = STATE_PATH / f"service-log-{service_id}.log"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
    except OSError:
        lines = []
    return {"service": service_id, "name": allowed[service_id][1], "lines": lines, "count": len(lines)}


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_services() -> dict:
    return {"accepted": True, "task": _queue("all", "refresh", "Refresh service status")}


@router.post("/{service_id}/restart", status_code=status.HTTP_202_ACCEPTED)
def restart_service(service_id: str, value: ServiceAction) -> dict:
    allowed = {item[0]: item for item in CATALOG if item[3]}
    if service_id not in allowed:
        raise HTTPException(status_code=400, detail="Service is unavailable or restart is protected")
    if not value.confirmed:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required")
    return {
        "accepted": True,
        "task": _queue(service_id, "restart", f"Restart {allowed[service_id][1]}"),
    }
