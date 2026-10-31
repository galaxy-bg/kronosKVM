"""Root-only physical LCD controls. No network API or arbitrary command input.

All slow work runs on one background worker; the GPIO/render loop reads a cache.
AP on/off is a runtime switch: normal boot provisioning restores the recovery AP.
"""

import fcntl
import importlib.util
import json
import logging
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ACTIONS = frozenset({"diagnostics", "ap-on", "ap-off", "access-on", "access-off",
                     "connect", "disconnect", "reboot", "poweroff"})


def run(args, required=True, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if required and result.returncode:
        raise RuntimeError("Host operation failed: " + args[0])
    return result


def read_json(path, fallback=None):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else (fallback or {})
    except (OSError, ValueError):
        return fallback or {}


class LocalLCDClient:
    def __init__(self, api, project="/opt/kronoskvm", state="/var/lib/kronoskvm/state"):
        self.api = api
        self.project = Path(project)
        self.state = Path(state)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lcd-control")
        self.lock = threading.Lock()
        self.cache = {}
        self.future = None
        self.next_refresh = 0
        self.busy = False

    def snapshot(self):
        with self.lock:
            if (not self.busy and (self.future is None or self.future.done())
                    and time.monotonic() >= self.next_refresh):
                self.next_refresh = time.monotonic() + 5
                self.future = self.worker.submit(self.safe_refresh)
            return self.cache.copy()

    def safe_refresh(self):
        try:
            self.refresh()
        except Exception:
            logging.getLogger(__name__).exception("LCD snapshot failed")
            with self.lock:
                self.cache.update(ready=False, errors=["Status unavailable"])

    def refresh(self):
        errors = []
        value = {}
        for key, path in (("info", "/system/info"), ("network", "/system/network"),
                          ("vpn", "/remote-assist")):
            try:
                value[key] = self.api.get(path)
            except (OSError, ValueError):
                errors.append(key + " unavailable")
                value[key] = {}
        value["ethernet_ip"] = next((address.split("/")[0]
            for item in value["network"].get("interfaces", []) if item["name"] == "eth0"
            for address in item.get("addresses", []) if ":" not in address), "No IP")
        try:
            active = run(["bash", "-c", 'source "$1"; active_management_ap_uuid',
                          "lcd", str(self.project / "scripts/management-ap.sh")], False)
            value["ap_enabled"] = active.returncode == 0
            value["ap_known"] = True
        except (OSError, subprocess.SubprocessError):
            errors.append("Wi-Fi unavailable")
            value["ap_known"] = False
        access = read_json(self.state / "ap-access-status.json")
        access["stale"] = time.time() - access.get("updated_at", 0) > 60
        if access["stale"]:
            access["state"] = "Unavailable"
        value["access"] = access
        units = ("kronoskvm-containers.service", "docker.service", "NetworkManager.service",
                 "dnsmasq.service", "infrabox-lcd.service", "kronoskvm-wifi.service",
                 "kronoskvm-ap-access.service")
        try:
            output = run(["systemctl", "show", "--property=Id,ActiveState,LoadState", *units],
                         False).stdout
            value["services"] = []
            for block in output.strip().split("\n\n"):
                fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
                label = fields.get("Id", "Unknown").removesuffix(".service")
                label = label.removeprefix("kronoskvm-")
                state = fields.get("ActiveState", "unknown")
                if fields.get("LoadState") == "not-found":
                    state = "not installed"
                value["services"].append(label + ": " + state)
        except (OSError, subprocess.SubprocessError):
            value["services"] = ["Service health unavailable"]
            errors.append("Service health unavailable")
        try:
            failed = run(["systemctl", "--failed", "--no-legend", "--plain"], False).stdout
            errors.extend(line.split()[0] for line in failed.splitlines() if line.strip())
        except (OSError, subprocess.SubprocessError):
            errors.append("Service health unavailable")
        value["errors"] = errors
        value["ready"] = bool(value["info"]) and not errors
        try:
            release = Path("/etc/kronoskvm/application-release").read_text()
            value["release"] = release.splitlines()[0]
        except (OSError, IndexError):
            value["release"] = "Unavailable"
        with self.lock:
            self.cache.update(value)

    def control(self, action):
        if action not in ACTIONS:
            raise ValueError("Unsupported LCD action")
        with self.lock:
            if self.busy:
                raise RuntimeError("Action already running")
            self.busy = True
            request_id = str(uuid.uuid4())
            self.worker.submit(self.perform, action, request_id)
        return request_id

    def host_module(self, name):
        path = self.project / "scripts" / (name + ".py")
        spec = importlib.util.spec_from_file_location("lcd_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def perform(self, action, request_id):
        result = {"request_id": request_id, "ok": False, "message": "Result unknown"}
        try:
            message = self.execute(action)
            result.update(ok=True, message=message)
            logging.getLogger(__name__).info("LCD action %s completed", action)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result["message"] = str(error)[:160]
            logging.getLogger(__name__).exception("LCD action %s failed", action)
        finally:
            try:
                self.refresh()
            except Exception:
                logging.getLogger(__name__).exception("LCD status refresh failed")
            with self.lock:
                self.cache["result"] = result
                self.busy = False

    def execute(self, action):
        if action == "diagnostics":
            rows = self.diagnostics()
            with self.lock:
                self.cache["diagnostics"] = rows
            return "Diagnostics complete"
        if action in {"ap-on", "ap-off"}:
            # Reuse the Wi-Fi controller lock so web updates cannot race this switch.
            with (self.state / "wifi.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if (self.state / "wifi-request.json").exists():
                    raise RuntimeError("Wi-Fi action pending")
                helper = str(self.project / "scripts/management-ap.sh")
                profile = run(["bash", "-c", 'source "$1"; management_ap_uuid', "lcd", helper])
                ap_uuid = str(uuid.UUID(profile.stdout.strip()))
                if action == "ap-on":
                    run(["nmcli", "--wait", "25", "connection", "up", "uuid", ap_uuid],
                        timeout=30)
                else:
                    active = run(["bash", "-c", 'source "$1"; active_management_ap_uuid',
                                  "lcd", helper], False)
                    if active.returncode == 0:
                        run(["nmcli", "--wait", "15", "connection", "down", "uuid", ap_uuid],
                            timeout=20)
                active = run(["bash", "-c", 'source "$1"; active_management_ap_uuid',
                              "lcd", helper], False)
                if (active.returncode == 0) != (action == "ap-on"):
                    raise RuntimeError("Wi-Fi AP state did not change")
            return "Wi-Fi AP " + ("enabled" if action == "ap-on" else "disabled until boot")
        if action in {"access-on", "access-off"}:
            helper = self.host_module("ap-access-host")
            with (self.state / "ap-access.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if (self.state / "ap-access-request.json").exists():
                    raise RuntimeError("Customer Access action pending")
                policy = helper.read_config()
                policy["enabled"] = action == "access-on"
                try:
                    helper.apply(policy)
                    helper.atomic(helper.CONFIG, json.dumps(policy))
                    helper.write_status(policy)
                except Exception:
                    helper.apply(helper.OFF)
                    helper.atomic(helper.CONFIG, json.dumps(helper.OFF))
                    helper.write_status(helper.OFF, "LCD policy apply failed")
                    raise
            return "Customer Access " + ("enabled" if policy["enabled"] else "disabled")
        if action in {"connect", "disconnect"}:
            before = self.api.status()
            if not before.get("installed") or before.get("stale", True):
                raise RuntimeError("VPN service unavailable")
            if before.get("pending"):
                raise RuntimeError("VPN action already pending")
            if action == "connect" and not before.get("profile"):
                raise RuntimeError("VPN profile required in Web UI")
            response = self.api.action("enable" if action == "connect" else "disable")
            deadline = time.monotonic() + 85
            while time.monotonic() < deadline:
                status = self.api.status()
                result = status.get("last_result") or {}
                if result.get("request_id") == response["request_id"]:
                    if not result.get("ok"):
                        raise RuntimeError("VPN action failed; check profile")
                    return "VPN: " + status.get("state", "unknown")
                time.sleep(1)
            raise RuntimeError("VPN result unknown; check status")
        if action in {"reboot", "poweroff"}:
            run(["systemctl", "--no-block", action])
            return "Restarting..." if action == "reboot" else "Shutting down..."
        raise ValueError("Unsupported LCD action")

    def diagnostics(self):
        rows = []
        carrier = Path("/sys/class/net/eth0/carrier")
        try:
            link = carrier.read_text().strip() == "1"
            rows.append("Ethernet: " + ("Link UP" if link else "No link"))
        except OSError:
            rows.append("Ethernet: Unavailable")
        routes_result = run(["ip", "-j", "-4", "route", "show", "default"], False)
        routes = json.loads(routes_result.stdout or "[]")
        gateway = next((r.get("gateway") for r in routes if r.get("dev") == "eth0"), None)
        rows.append("IP: " + self.cache.get("ethernet_ip", "No IP"))
        rows.append("Gateway: " + (gateway or "Missing"))
        if gateway:
            reachable = run(["ping", "-I", "eth0", "-c", "1", "-W", "2", gateway], False)
            rows.append("GW ping: " + ("OK" if reachable.returncode == 0 else "No reply"))
        try:
            dns = run(["getent", "ahostsv4", "example.com"], False, timeout=5)
        except subprocess.TimeoutExpired:
            dns = subprocess.CompletedProcess([], 1)
        rows.append("DNS: " + ("OK" if dns.returncode == 0 else "Failed"))
        internet = run(["ping", "-c", "1", "-W", "2", "1.1.1.1"], False)
        rows.append("Internet ping: " + ("OK" if internet.returncode == 0 else "No reply"))
        return rows
