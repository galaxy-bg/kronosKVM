"""Four-button local menu, independent of the LCD driver."""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

# Physical enclosure order: down, up, menu/select, back to top level.
PINS = {"down": 5, "up": 6, "ok": 19, "back": 13}
ITEMS = (
    ("Destegi ac", "enable"),
    ("Destegi kapat", "disable"),
    ("Acilista ac", "boot-on"),
    ("Acilista kapat", "boot-off"),
)


class KeyScanner:
    """Debounced release events; startup holds and multi-key chords are ignored."""

    def __init__(self):
        self.armed = False
        self.candidate = None
        self.chord = False
        self.last_active = None
        self.changed_at = 0

    def update(self, active, now):
        active = frozenset(active)
        if active != self.last_active:
            self.last_active, self.changed_at = active, now
        if now - self.changed_at < 0.08:
            return None
        if not active:
            key = self.candidate if self.armed and not self.chord else None
            self.armed, self.candidate, self.chord = True, None, False
            return key
        if self.armed:
            if len(active) > 1 or (self.candidate and self.candidate not in active):
                self.chord = True
            elif not self.chord:
                self.candidate = next(iter(active))
        return None


class RemoteAssistClient:
    def __init__(self, base_url="http://127.0.0.1:8000",
                 token_path="/etc/kronoskvm/lcd-api-token"):
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.url = self.base_url + "/remote-assist"
        self.token_path = Path(token_path)

    def request(self, path, method="GET"):
        token = self.token_path.read_text(encoding="ascii").strip()
        request = Request(self.base_url + path, method=method,
                          data=b"" if method == "POST" else None,
                          headers={"X-KDX-LCD-Token": token})
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def get(self, path):
        return self.request(path)

    def status(self):
        return self.request("/remote-assist")

    def action(self, action):
        if action not in {item[1] for item in ITEMS}:
            raise ValueError("Unsupported keypad action")
        return self.request("/remote-assist/" + action, method="POST")


class Menu:
    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.selected = 0
        self.in_menu = False
        self.confirm = None
        self.confirm_until = 0
        self.pending = None
        self.pending_since = 0
        self.status = {}
        self.message = ""

    def refresh(self):
        try:
            self.status = self.client.status()
        except (OSError, ValueError):
            self.status = {}
        if self.confirm and self.clock() >= self.confirm_until:
            self.confirm = None
        if self.pending:
            result = self.status.get("last_result") or {}
            if result.get("request_id") == self.pending:
                self.message = "Tamamlandi" if result.get("ok") else "Islem basarisiz"
                self.pending = None
            elif self.clock() - self.pending_since >= 90:
                self.message = "Sonuc belirsiz"
                self.pending = None

    def ready(self):
        return (
            self.status.get("installed")
            and not self.status.get("stale", True)
            and not self.status.get("pending")
            and not self.pending
        )

    def press(self, key):
        if key not in PINS:
            return
        self.refresh()
        if key == "back":
            self.confirm = None
            self.in_menu = False
            self.message = ""
            return
        if self.pending:
            return
        if key in {"up", "down"}:
            self.in_menu = True
            self.confirm = None
            self.message = ""
            self.selected = (self.selected + (1 if key == "down" else -1)) % len(ITEMS)
            return
        if not self.in_menu:
            self.in_menu = True
            return
        if not self.ready():
            self.confirm = None
            self.message = "Servis hazir degil"
            return
        action = ITEMS[self.selected][1]
        if action == "enable" and not self.status.get("profile"):
            self.confirm = None
            self.message = "Once VPN profili"
            return
        if self.confirm != action:
            self.confirm = action
            self.confirm_until = self.clock() + 10
            self.message = ""
            return
        self.confirm = None
        try:
            result = self.client.action(action)
            self.pending = result["request_id"]
            self.pending_since = self.clock()
            self.message = ""
        except (OSError, ValueError, KeyError):
            # A timed-out HTTP call may have reached the host. Never claim failure/success.
            self.message = "Sonuc belirsiz"

    def lines(self):
        if not self.status.get("installed") or self.status.get("stale", True):
            return ("Remote Assist", "Durum alinamiyor")
        if self.pending or self.status.get("pending"):
            return ("Remote Assist", "Uygulaniyor...")
        if self.message:
            return ("Remote Assist", self.message)
        if self.confirm:
            return (ITEMS[self.selected][0] + "?", "OK:Onay BACK:Iptal")
        if self.in_menu:
            return ("Remote Assist", ITEMS[self.selected][0])
        states = {
            "off": "Kapali", "connected": "VPN bagli",
            "waiting_handshake": "VPN bekleniyor", "disconnected": "VPN bagli degil",
            "setup_required": "Profil gerekli", "stop_failed": "Kapatma hatasi",
        }
        return ("Remote Assist", states.get(self.status.get("state"), "Durum bilinmiyor"))


SECTIONS = ("Status", "Network", "Remote Assist", "System")


class MainMenu:
    """Small local operations UI; hardware work is delegated to an async client."""

    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.remote = Menu(client)  # Retained for renderer compatibility.
        self.selected = 0
        self.section = "Status"
        self.page = None
        self.offset = 0
        self.details = []
        self.data = {}
        self.confirm = None
        self.confirm_selected = 0
        self.confirm_until = 0
        self.pending = None
        self.message = ""
        self.last_input = clock()

    def refresh(self):
        self.data = self.client.snapshot()
        self.remote.status = self.data.get("vpn", {})
        now = self.clock()
        if self.confirm and now >= self.confirm_until:
            self.confirm = None
        result = self.data.get("result", {})
        if self.pending and result.get("request_id") == self.pending:
            self.message = result.get("message", "Completed" if result.get("ok") else "Failed")
            self.pending = None
        if now - self.last_input >= 30 and not self.pending:
            self.section, self.page, self.offset = "Status", None, 0
            self.confirm, self.message = None, ""
        self.details = self.rows()
        self.offset = min(self.offset, max(0, len(self.details) - 4))

    def options(self):
        if self.section == "Network":
            return [("Network Diagnostics", "diagnostics"),
                    ("Wi-Fi AP: " + ("Disable" if self.data.get("ap_enabled") else "Enable"),
                     "ap-off" if self.data.get("ap_enabled") else "ap-on"),
                    ("Customer: " +
                     ("Disable" if self.data.get("access", {}).get("enabled") else "Enable"),
                     "access-off" if self.data.get("access", {}).get("enabled") else "access-on")]
        if self.section == "Remote Assist":
            active = self.data.get("vpn", {}).get("enabled", False)
            return [("VPN Status", "vpn-status"),
                    ("Disconnect" if active else "Connect", "disconnect" if active else "connect")]
        if self.section == "System":
            return [("Device Information", "device"), ("Service Health", "services"),
                    ("Restart", "reboot"), ("Shutdown", "poweroff")]
        return []

    def rows(self):
        d = self.data
        if self.page == "diagnostics":
            return d.get("diagnostics", ["OK: Run diagnostics"])
        if self.page == "vpn-status":
            vpn = d.get("vpn", {})
            return ["VPN: " + str(vpn.get("state", "unavailable")),
                    "IP: " + str((vpn.get("profile") or {}).get("address") or "--"),
                    "Profile: " + str((vpn.get("profile") or {}).get("name", "Missing"))]
        if self.page == "device":
            info = d.get("info", {})
            return [str(info.get("hostname", "Unavailable")),
                    "Model: " + str(info.get("model", "--")),
                    "S/N: " + str(info.get("serial", "--")),
                    "Uptime: " + str(int(info.get("uptime_seconds", 0)) // 60) + " min",
                    "Release: " + str(d.get("release", "--"))]
        if self.page == "services":
            return d.get("services", ["Unavailable"])
        errors = d.get("errors", [])
        return (["Error: " + str(errors[0]) if errors else
                 ("System Ready" if d.get("ready") else "Starting / Unavailable")]
                + ["ETH: " + str(d.get("ethernet_ip", "No IP")),
                   "Wi-Fi AP: " + ("ON" if d.get("ap_enabled") else "OFF"),
                   "Customer Access: " + str(d.get("access", {}).get("state", "Unavailable")),
                   "VPN: " + str(d.get("vpn", {}).get("state", "Unavailable"))])

    def press(self, key):
        if key not in PINS:
            return
        self.refresh()
        self.last_input = self.clock()
        if key == "back":
            if self.section in SECTIONS:
                self.selected = SECTIONS.index(self.section)
            self.section, self.page, self.offset = None, None, 0
            self.confirm, self.message = None, ""
            return
        if self.confirm:
            if key in {"up", "down"}:
                self.confirm_selected = 1 - self.confirm_selected
            elif key == "ok":
                action, self.confirm = self.confirm, None
                if self.confirm_selected == 1:
                    try:
                        self.pending = self.client.control(action)
                        self.message = "Working..."
                        if action == "diagnostics":
                            self.page = "diagnostics"
                    except (OSError, ValueError, RuntimeError) as error:
                        self.message = str(error)
            return
        if self.pending:
            return
        if self.message:
            if key == "ok":
                self.message = ""
            return
        if self.section is None:
            if key in {"up", "down"}:
                self.selected = (self.selected + (1 if key == "down" else -1)) % len(SECTIONS)
            elif key == "ok":
                self.section, self.selected, self.offset = SECTIONS[self.selected], 0, 0
        elif self.section == "Status" or self.page:
            if key in {"up", "down"}:
                self.offset = max(0, min(max(0, len(self.rows()) - 4),
                                        self.offset + (1 if key == "down" else -1)))
            elif key == "ok":
                if self.section == "Status":
                    self.section, self.selected = None, 0
                elif self.page == "diagnostics":
                    self.start_confirmation("diagnostics")
        else:
            options = self.options()
            if key in {"up", "down"}:
                self.selected = (self.selected + (1 if key == "down" else -1)) % len(options)
            elif key == "ok":
                action = options[self.selected][1]
                if action in {"device", "services", "vpn-status"}:
                    self.page, self.offset = action, 0
                else:
                    self.start_confirmation(action)

    def start_confirmation(self, action):
        self.confirm = action
        self.confirm_selected = 0  # Cancel is always the default.
        self.confirm_until = self.clock() + 15

    def view(self):
        if self.confirm:
            hints = {"ap-off": "Wi-Fi will disconnect", "access-on": "Wi-Fi to customer LAN",
                     "poweroff": "Power will turn off", "reboot": "Device will restart"}
            return {"title": "Confirm " + self.confirm, "items": ["Cancel", "Confirm"],
                    "selected": self.confirm_selected,
                    "subtitle": hints.get(self.confirm, "Apply this action?")}
        if self.pending or self.message:
            return {"title": self.section or "LCD", "rows": [self.message or "Working..."],
                    "subtitle": "Please wait" if self.pending else "Action result"}
        if self.section is None:
            return {"title": "InfraBox / Menu", "items": list(SECTIONS),
                    "selected": self.selected}
        if self.section != "Status" and not self.page:
            return {"title": self.section, "items": [item[0] for item in self.options()],
                    "selected": self.selected}
        return {"title": self.page or self.section, "rows": self.rows(), "offset": self.offset}

    def lines(self):
        view = self.view()
        rows = view.get("items", view.get("rows", []))
        index = view.get("selected", view.get("offset", 0))
        return view["title"], rows[index] if rows else "Unavailable"
